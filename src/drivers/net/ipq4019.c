/*
 * Copyright 2026 Google LLC / contributors.
 *
 * IPQ4019 (Google Wifi "gale") ESS EDMA ethernet driver for depthcharge.
 *
 * EDMA ring/switch/eth logic ported from mainline U-Boot drivers/net/essedma.c
 * (GPL-2.0+, Robert Marko / Gabor Juhos, Sartura). depthcharge NetDevice
 * integration (INIT_FUNC -> NetPoller -> lazy init -> net_add_device, coreboot
 * MAC handling, cache-coherent DMA) follows src/drivers/net/ipq806x.c.
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; either version 2 of
 * the License, or (at your option) any later version.
 */

#include <libpayload.h>
#include <arch/cache.h>
#include <sysinfo.h>

#include "base/init_funcs.h"
#include "drivers/net/net.h"
#include "drivers/net/ipq4019.h"

#define EDMA_TXQ_ID		0
#define EDMA_RXQ_ID		0
#define NO_OF_TX_DESC		IPQ4019_EDMA_TX_RING_SIZE	/* 8 */
#define NO_OF_RX_DESC		128
#define EDMA_RX_BUF_SIZE	2048		/* RRD(16) + frame, cache-aligned */

/* One TPD suffices for a packet, but a cache line is bigger than one 16-byte
 * TPD and we cannot flush a single TPD in isolation, so send each packet as
 * 4 TPDs (matches U-Boot). */
#define EDMA_TPDS_PER_PACKET	4
#define EDMA_TPD_MIN_BYTES	4
#define EDMA_MIN_PKT_SIZE	(EDMA_TPDS_PER_PACKET * EDMA_TPD_MIN_BYTES)
#define EDMA_TX_COMPLETE_TIMEOUT 1000000

typedef struct {
	void *base;		/* EDMA register base */
	void *esw;		/* switch register base */
	uip_eth_addr mac_addr;
	int started;

	edma_tpd *tpd_ring;	/* TX descriptor ring (virt) */
	edma_rfd *rfd_ring;	/* RX free descriptor ring (virt) */
	uint16_t tpd_head, tpd_tail;
	uint16_t rfd_head, rfd_tail;
} IpqEdmaDev;

static void *net_rx_packets[NO_OF_RX_DESC];

/* ---- helpers ---- */
static inline void flush_range(void *addr, size_t len)
{
	dcache_clean_invalidate_by_mva(addr, len);
}
static inline void invalidate_range(void *addr, size_t len)
{
	dcache_invalidate_by_mva(addr, len);
}

/*
 * MAC address: prefer the coreboot sysinfo table (gale coreboot fills in the
 * switch MACs); otherwise synthesise a locally-administered one. Mirrors
 * ipq806x.c get_eth_mac_address().
 */
static int get_eth_mac_address(uint8_t *enetaddr)
{
	int i, valid = 0;

	for (i = 0; i < 6; i++) {
		enetaddr[i] = lib_sysinfo.macs[0].mac_addr[i];
		if (enetaddr[i])
			valid = 1;
	}
	if (!valid) {
		printf("ipq4019: no MAC in sysinfo, using locally-administered\n");
		enetaddr[0] = 0x02;
		enetaddr[1] = 0x00;
		enetaddr[2] = 0xc0;	/* placeholder OUI-ish tail */
		enetaddr[3] = 0xff;
		enetaddr[4] = 0xee;
		enetaddr[5] = 0x01;
	}
	return 1;
}

/* ---- ESS switch ---- */
static void ess_switch_disable_lookup(IpqEdmaDev *p)
{
	int i, vid;
	uint32_t val;

	for (i = 0; i < ESS_PORTS_NUM; i++) {
		val = readl(p->esw + ESS_PORT_LOOKUP_CTRL(i));
		val &= ~ESS_PORT_VID_MEM_MASK;
		if (i == 0 || i == 5)
			vid = 0;			/* CPU, WAN -> nothing */
		else
			vid = 0x1e & ~(1 << i);		/* LAN -> other LANs */
		val |= vid & ESS_PORT_VID_MEM_MASK;
		writel(val, p->esw + ESS_PORT_LOOKUP_CTRL(i));
	}
	writel(0x3e3e3e, p->esw + ESS_GLOBAL_FW_CTRL1);
}

static void ess_switch_enable_lookup(IpqEdmaDev *p)
{
	int i, vid;
	uint32_t val;

	for (i = 0; i < ESS_PORTS_NUM; i++) {
		val = readl(p->esw + ESS_PORT_LOOKUP_CTRL(i));
		val &= ~ESS_PORT_VID_MEM_MASK;
		if (i == 0)
			vid = 0x3e;			/* CPU -> all others */
		else if (i == 5)
			vid = 0x01;			/* WAN -> CPU only */
		else
			vid = 0x1f & ~(1 << i);		/* LAN -> CPU+other LAN */
		val |= vid & ESS_PORT_VID_MEM_MASK;
		writel(val, p->esw + ESS_PORT_LOOKUP_CTRL(i));
	}
	writel(0x3f3f3f, p->esw + ESS_GLOBAL_FW_CTRL1);
}

static void ess_switch_init(IpqEdmaDev *p)
{
	uint32_t val = 0;
	int i;

	writel(0x3e3e3e, p->esw + ESS_GLOBAL_FW_CTRL1);

	/* CPU port (0): 1000M, full duplex, flow control. */
	val = ESS_PORT_SPEED_1000 | ESS_PORT_DUPLEX_MODE |
	      ESS_PORT_TX_FLOW_EN | ESS_PORT_RX_FLOW_EN;
	writel(val, p->esw + ESS_PORT0_STATUS);

	for (i = 0; i < ESS_PORTS_NUM; i++) {
		val = readl(p->esw + ESS_PORT_LOOKUP_CTRL(i));
		val &= ~ESS_PORT_VID_MEM_MASK;
		writel(val, p->esw + ESS_PORT_LOOKUP_CTRL(i));
	}

	/* HOL settings */
	for (i = 0; i < ESS_PORTS_NUM; i++) {
		val = (30 << EG_PORT_QUEUE_NUM_SHIFT);
		if (i == 0 || i == 5) {
			val |= (4 << EG_PRI5_QUEUE_NUM_SHIFT);
			val |= (4 << EG_PRI4_QUEUE_NUM_SHIFT);
		}
		val |= (4 << EG_PRI3_QUEUE_NUM_SHIFT);
		val |= (4 << EG_PRI2_QUEUE_NUM_SHIFT);
		val |= (4 << EG_PRI1_QUEUE_NUM_SHIFT);
		val |= (4 << EG_PRI0_QUEUE_NUM_SHIFT);
		writel(val, p->esw + ESS_PORT_HOL_CTRL0(i));

		val = readl(p->esw + ESS_PORT_HOL_CTRL1(i));
		val &= ~ESS_ING_BUF_NUM_0_MASK;
		val |= 6 & ESS_ING_BUF_NUM_0_MASK;
		writel(val, p->esw + ESS_PORT_HOL_CTRL1(i));
	}
	mdelay(1);

	val = readl(p->esw + ESS_PORT0_STATUS);
	val |= ESS_PORT_TXMAC_EN | ESS_PORT_RXMAC_EN;
	writel(val, p->esw + ESS_PORT0_STATUS);

	writel(0x7f7f7f, p->esw + ESS_GLOBAL_FW_CTRL1);
}

/* ---- EDMA ---- */
static void edma_stop_rx_tx(IpqEdmaDev *p)
{
	uint32_t d;

	d = readl(p->base + EDMA_REG_RXQ_CTRL);
	d &= ~EDMA_RXQ_CTRL_EN;
	writel(d, p->base + EDMA_REG_RXQ_CTRL);
	d = readl(p->base + EDMA_REG_TXQ_CTRL);
	d &= ~EDMA_TXQ_CTRL_TXQ_EN;
	writel(d, p->base + EDMA_REG_TXQ_CTRL);
}

static void edma_start_rx_tx(IpqEdmaDev *p)
{
	uint32_t d;

	d = readl(p->base + EDMA_REG_RXQ_CTRL);
	d |= EDMA_RXQ_CTRL_EN;
	writel(d, p->base + EDMA_REG_RXQ_CTRL);
	d = readl(p->base + EDMA_REG_TXQ_CTRL);
	d |= EDMA_TXQ_CTRL_TXQ_EN;
	writel(d, p->base + EDMA_REG_TXQ_CTRL);
}

static void edma_configure(IpqEdmaDev *p)
{
	uint32_t tmp;
	int i;

	writel(IPQ4019_EDMA_RSS_TYPE_NONE, p->base + EDMA_REG_RSS_TYPE);
	for (i = 0; i < EDMA_NUM_IDT; i++)
		writel(EDMA_RSS_IDT_VALUE, p->base + EDMA_REG_RSS_IDT(i));

	tmp = (EDMA_RFD_BURST << EDMA_RXQ_RFD_BURST_NUM_SHIFT);
	tmp |= (EDMA_RFD_THR << EDMA_RXQ_RFD_PF_THRESH_SHIFT);
	tmp |= (EDMA_RFD_LTHR << EDMA_RXQ_RFD_LOW_THRESH_SHIFT);
	writel(tmp, p->base + EDMA_REG_RX_DESC1);

	tmp = EDMA_FIFO_THRESH_128_BYTE | EDMA_RXQ_CTRL_RMV_VLAN;
	writel(tmp, p->base + EDMA_REG_RXQ_CTRL);

	tmp = (EDMA_TPD_BURST << EDMA_TXQ_NUM_TPD_BURST_SHIFT);
	tmp |= EDMA_TXQ_CTRL_TPD_BURST_EN;
	tmp |= (EDMA_TXF_BURST << EDMA_TXQ_TXF_BURST_NUM_SHIFT);
	writel(tmp, p->base + EDMA_REG_TXQ_CTRL);
}

static void edma_init_desc(IpqEdmaDev *p)
{
	uint32_t data, hw_cons;

	/* TX */
	writel((uint32_t)virt_to_phys(p->tpd_ring),
	       p->base + EDMA_REG_TPD_BASE_ADDR_Q(EDMA_TXQ_ID));
	data = readl(p->base + EDMA_REG_TPD_IDX_Q(EDMA_TXQ_ID));
	hw_cons = (data >> EDMA_TPD_CONS_IDX_SHIFT) & EDMA_TPD_CONS_IDX_MASK;
	p->tpd_head = hw_cons;
	p->tpd_tail = hw_cons;
	data &= ~EDMA_TPD_PROD_IDX_MASK;
	data |= hw_cons;
	writel(data, p->base + EDMA_REG_TPD_IDX_Q(EDMA_TXQ_ID));
	writel(hw_cons, p->base + EDMA_REG_TX_SW_CONS_IDX_Q(EDMA_TXQ_ID));
	writel(NO_OF_TX_DESC & EDMA_TPD_RING_SIZE_MASK,
	       p->base + EDMA_REG_TPD_RING_SIZE);

	/* RX */
	writel((uint32_t)virt_to_phys(p->rfd_ring),
	       p->base + EDMA_REG_RFD_BASE_ADDR_Q(EDMA_RXQ_ID));
	data = (NO_OF_RX_DESC & EDMA_RFD_RING_SIZE_MASK) << EDMA_RFD_RING_SIZE_SHIFT;
	data |= (EDMA_RX_BUF_SIZE & EDMA_RX_BUF_SIZE_MASK) << EDMA_RX_BUF_SIZE_SHIFT;
	writel(data, p->base + EDMA_REG_RX_DESC0);

	writel(0, p->base + EDMA_REG_TXF_WATER_MARK);

	data = readl(p->base + EDMA_REG_TX_SRAM_PART);
	data |= 1 << EDMA_LOAD_PTR_SHIFT;
	writel(data, p->base + EDMA_REG_TX_SRAM_PART);
}

static void edma_init_rfd_ring(IpqEdmaDev *p)
{
	int i;

	for (i = 0; i < NO_OF_RX_DESC; i++)
		p->rfd_ring[i].buffer_addr = (uint32_t)virt_to_phys(net_rx_packets[i]);
	flush_range(p->rfd_ring, NO_OF_RX_DESC * sizeof(edma_rfd));

	p->rfd_head = NO_OF_RX_DESC - 1;
	p->rfd_tail = 0;
	writel(p->rfd_head, p->base + EDMA_REG_RFD_IDX_Q(EDMA_RXQ_ID));
}

static int edma_alloc_rings(IpqEdmaDev *p)
{
	int i;
	int cl = dcache_line_bytes();

	p->tpd_ring = xmemalign(cl, ALIGN_UP(NO_OF_TX_DESC * sizeof(edma_tpd), cl));
	p->rfd_ring = xmemalign(cl, ALIGN_UP(NO_OF_RX_DESC * sizeof(edma_rfd), cl));
	if (!p->tpd_ring || !p->rfd_ring)
		return -1;
	memset(p->tpd_ring, 0, NO_OF_TX_DESC * sizeof(edma_tpd));
	memset(p->rfd_ring, 0, NO_OF_RX_DESC * sizeof(edma_rfd));

	for (i = 0; i < NO_OF_RX_DESC; i++) {
		net_rx_packets[i] = xmemalign(cl, EDMA_RX_BUF_SIZE);
		if (!net_rx_packets[i])
			return -1;
	}
	p->tpd_head = p->tpd_tail = 0;
	p->rfd_head = p->rfd_tail = 0;
	return 0;
}

/* ---- NetDevice ops ---- */
static int ipq4019_eth_send(NetDevice *dev, void *packet, uint16_t length)
{
	IpqEdmaDev *p = dev->dev_data;
	edma_tpd *tpd, *first = NULL;
	int i, len = length;

	if (length < EDMA_MIN_PKT_SIZE)
		return 0;

	flush_range(packet, ALIGN_UP(length, dcache_line_bytes()));

	for (i = 0; i < EDMA_TPDS_PER_PACKET; i++) {
		void *frag = (uint8_t *)packet + i * EDMA_TPD_MIN_BYTES;

		tpd = &p->tpd_ring[p->tpd_head];
		if (i == 0)
			first = tpd;
		p->tpd_head++;
		if (p->tpd_head == NO_OF_TX_DESC)
			p->tpd_head = 0;

		tpd->svlan_tag = 0;
		tpd->addr = (uint32_t)virt_to_phys(frag);
		tpd->word3 = EDMA_PORT_ENABLE_ALL << EDMA_TPD_PORT_BITMAP_SHIFT;
		if (i < EDMA_TPDS_PER_PACKET - 1) {
			tpd->len = EDMA_TPD_MIN_BYTES;
			tpd->word1 = 0;
		} else {
			/*
			 * EOP TPD takes the FULL original frame length (the
			 * hardware uses this to determine total frame size,
			 * not just the last fragment's size). U-Boot's
			 * ipq40xx_eth_send confirms: tpd->len = length (the
			 * original parameter), not the decremented running
			 * counter.
			 */
			tpd->len = length;
			tpd->word1 = 1 << EDMA_TPD_EOP_SHIFT;
		}
		len -= EDMA_TPD_MIN_BYTES;
	}

	flush_range(first, EDMA_TPDS_PER_PACKET * sizeof(edma_tpd));
	writel(p->tpd_head, p->base + EDMA_REG_TPD_IDX_Q(EDMA_TXQ_ID));

	for (i = 0; i < EDMA_TX_COMPLETE_TIMEOUT; i++) {
		uint32_t r = readl(p->base + EDMA_REG_TPD_IDX_Q(EDMA_TXQ_ID));
		uint32_t prod = r & EDMA_TPD_PROD_IDX_MASK;
		uint32_t cons = (r >> EDMA_TPD_CONS_IDX_SHIFT) & EDMA_TPD_CONS_IDX_MASK;
		if (cons == prod)
			break;
		udelay(1);
	}
	if (i == EDMA_TX_COMPLETE_TIMEOUT)
		printf("ipq4019: TX timeout\n");

	writel(p->tpd_head, p->base + EDMA_REG_TX_SW_CONS_IDX_Q(EDMA_TXQ_ID));
	return 0;
}

static int ipq4019_eth_recv(NetDevice *dev, void *buf, uint16_t *len, int maxlen)
{
	IpqEdmaDev *p = dev->dev_data;
	uint32_t hw_tail;
	uint8_t *rx_pkt;
	edma_rrd *rrd;
	uint16_t length;

	*len = 0;

	hw_tail = readl(p->base + EDMA_REG_RFD_IDX_Q(EDMA_RXQ_ID));
	hw_tail = (hw_tail >> EDMA_RFD_CONS_IDX_SHIFT) & EDMA_RFD_CONS_IDX_MASK;
	if (hw_tail == p->rfd_tail)
		return 0;		/* nothing received */

	rx_pkt = net_rx_packets[p->rfd_tail];
	invalidate_range(rx_pkt, EDMA_RX_BUF_SIZE);
	rrd = (edma_rrd *)rx_pkt;

	if (!(rrd->rrd7 & EDMA_RRD7_DESC_VALID))
		return 0;

	length = rrd->rrd6;
	if (length > maxlen)
		length = maxlen;
	memcpy(buf, rx_pkt + EDMA_RRD_SIZE, length);
	*len = length;

	/* recycle the descriptor */
	writel(p->rfd_head, p->base + EDMA_REG_RFD_IDX_Q(EDMA_RXQ_ID));
	p->rfd_head++;
	if (p->rfd_head == NO_OF_RX_DESC)
		p->rfd_head = 0;
	p->rfd_tail++;
	if (p->rfd_tail == NO_OF_RX_DESC)
		p->rfd_tail = 0;
	writel(p->rfd_tail, p->base + EDMA_REG_RX_SW_CONS_IDX_Q(EDMA_RXQ_ID));
	return 0;
}

static int ipq4019_eth_start(IpqEdmaDev *p)
{
	edma_init_rfd_ring(p);
	edma_start_rx_tx(p);
	ess_switch_enable_lookup(p);
	p->started = 1;
	return 0;
}

static int ipq4019_phy_check_link(NetDevice *dev, int *ready)
{
	IpqEdmaDev *p = dev->dev_data;
	int i;

	if (!p->started)
		ipq4019_eth_start(p);

	*ready = 0;
	for (i = 0; i < IPQ4019_NUM_PORT_PHY; i++) {
		uint16_t v = 0;
		ipq4019_mdio_read(i, QCA807X_PHY_SPECIFIC, &v);
		if (v & QCA807X_PHY_SPECIFIC_LINK) {
			*ready = 1;
			break;
		}
	}
	return 0;
}

static const uip_eth_addr *ipq4019_get_mac(NetDevice *dev)
{
	IpqEdmaDev *p = dev->dev_data;
	return &p->mac_addr;
}

static int ipq4019_eth_write_hwaddr(IpqEdmaDev *p)
{
	uint8_t *m = p->mac_addr.addr;
	uint32_t lo, hi;

	hi = ((uint32_t)m[0] << 8) | m[1];
	lo = ((uint32_t)m[2] << 24) | ((uint32_t)m[3] << 16) |
	     ((uint32_t)m[4] << 8) | m[5];
	writel(lo, p->base + REG_MAC_CTRL0);
	writel(hi, p->base + REG_MAC_CTRL1);
	return 0;
}

/* ---- one-time bring-up ---- */
static int ipq4019_eth_init(void)
{
	NetDevice *dev;
	IpqEdmaDev *p;

	dev = xzalloc(sizeof(*dev));
	p = xzalloc(sizeof(*p));
	dev->dev_data = p;
	p->base = (void *)IPQ4019_EDMA_BASE;
	p->esw = (void *)IPQ4019_ESS_BASE;

	get_eth_mac_address(p->mac_addr.addr);
	printf("ipq4019: MAC %02x:%02x:%02x:%02x:%02x:%02x\n",
	       p->mac_addr.addr[0], p->mac_addr.addr[1], p->mac_addr.addr[2],
	       p->mac_addr.addr[3], p->mac_addr.addr[4], p->mac_addr.addr[5]);

	ipq4019_mdio_init();
	if (ipq4019_psgmii_self_test()) {
		/*
		 * PSGMII calibration did not converge — the SerDes is in an
		 * indeterminate state and no PHY will get link. Return -1 so
		 * the NetPoller retries eth_init on the next poll (the poller
		 * left `initted` 0 in that case). One transient miscalibration
		 * isn't fatal; we'll try again.
		 */
		printf("ipq4019: PSGMII calibration failed; will retry\n");
		return -1;
	}
	ess_switch_init(p);

	if (edma_alloc_rings(p)) {
		printf("ipq4019: ring alloc failed\n");
		return -1;
	}
	edma_stop_rx_tx(p);
	edma_configure(p);
	edma_init_desc(p);
	ess_switch_disable_lookup(p);
	ipq4019_eth_write_hwaddr(p);

	dev->ready = ipq4019_phy_check_link;
	dev->recv = ipq4019_eth_recv;
	dev->send = ipq4019_eth_send;
	dev->get_mac = ipq4019_get_mac;

	net_add_device(dev);
	return 0;
}

/*
 * Bounded-retry poller. Each NetPoller invocation may call eth_init() until
 * it succeeds OR we hit IPQ4019_ETH_INIT_MAX_RETRIES (3). If we exhaust the
 * retries, we STOP calling eth_init and let depthcharge's net layer just
 * report "no link" — this keeps the AP idle (not endlessly retrying MDIO/
 * PSGMII calibration) so the EC's SuzyQ bridge can access the SPI bus for
 * a follow-up driver re-flash. This converts an unrecoverable retry loop
 * into a recoverable failed-but-quiet state.
 */
#define IPQ4019_ETH_INIT_MAX_RETRIES 3
static void ipq4019_net_poller(struct NetPoller *poller)
{
	static int initted;
	static int retry_count;
	static int gave_up;

	if (initted || gave_up)
		return;
	if (retry_count >= IPQ4019_ETH_INIT_MAX_RETRIES) {
		printf("ipq4019: eth_init failed %d times — giving up "
		       "(driver halted, SuzyQ bus should now be accessible)\n",
		       retry_count);
		gave_up = 1;
		return;
	}
	retry_count++;
	printf("ipq4019: eth_init attempt %d/%d\n",
	       retry_count, IPQ4019_ETH_INIT_MAX_RETRIES);
	if (!ipq4019_eth_init())
		initted = 1;
}

static NetPoller net_poller = {
	.poll = ipq4019_net_poller,
};

static int ipq4019_eth_driver_register(void)
{
	list_insert_after(&net_poller.list_node, &net_pollers);
	return 0;
}

INIT_FUNC(ipq4019_eth_driver_register);

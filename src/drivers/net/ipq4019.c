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

	/* DSB SY: drain the CPU store buffer so the TPD field stores above
	 * are committed before the cache flush + doorbell. Matches `wmb()` in
	 * U-Boot's ipq40xx_eth_send (essedma.c:927); without this barrier the
	 * partial/stale TPD lines get written back to RAM, EDMA reads garbage
	 * addr/len, increments cons==prod, but never actually emits a frame. */
	asm volatile("dsb sy" ::: "memory");

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
		printf("ipq4019: TX timeout (frame len=%d)\n", length);

	{
		static int n_tx;
		if (n_tx == 0) {
			/* Switch port status + lookup-ctrl dump. */
			int sp;
			for (sp = 0; sp < ESS_PORTS_NUM; sp++) {
				printf("ipq4019: PORT%d_STATUS=0x%08x  LOOKUP_CTRL=0x%08x\n",
				       sp,
				       readl(p->esw + 0x7c + sp * 0x4),
				       readl(p->esw + ESS_PORT_LOOKUP_CTRL(sp)));
			}
			printf("ipq4019: FW_CTRL1=0x%08x\n",
			       readl(p->esw + ESS_GLOBAL_FW_CTRL1));
			/* One-shot EDMA register state dump on first TX. */
			printf("ipq4019: TPD_BASE     = 0x%08x  (want 0x%08x)\n",
			       readl(p->base + EDMA_REG_TPD_BASE_ADDR_Q(EDMA_TXQ_ID)),
			       (uint32_t)virt_to_phys(p->tpd_ring));
			printf("ipq4019: TPD_RING_SZ  = 0x%08x  (want %d)\n",
			       readl(p->base + EDMA_REG_TPD_RING_SIZE),
			       NO_OF_TX_DESC);
			printf("ipq4019: TXQ_CTRL     = 0x%08x  (TXQ_EN bit 0x20)\n",
			       readl(p->base + EDMA_REG_TXQ_CTRL));
			printf("ipq4019: RXQ_CTRL     = 0x%08x  (RXQ_EN 0xff00)\n",
			       readl(p->base + EDMA_REG_RXQ_CTRL));
			printf("ipq4019: TX_SRAM_PART = 0x%08x  (LOAD_PTR bit 0x%x)\n",
			       readl(p->base + EDMA_REG_TX_SRAM_PART),
			       1 << EDMA_LOAD_PTR_SHIFT);
			printf("ipq4019: TPD_IDX_Q    = 0x%08x  prod=0x%x cons=0x%x\n",
			       readl(p->base + EDMA_REG_TPD_IDX_Q(EDMA_TXQ_ID)),
			       readl(p->base + EDMA_REG_TPD_IDX_Q(EDMA_TXQ_ID)) & EDMA_TPD_PROD_IDX_MASK,
			       (readl(p->base + EDMA_REG_TPD_IDX_Q(EDMA_TXQ_ID)) >> EDMA_TPD_CONS_IDX_SHIFT) & EDMA_TPD_CONS_IDX_MASK);
			/* TPD content of first descriptor (the one we just wrote) */
			printf("ipq4019: first TPD virt=%p phys=0x%08x len=%d addr=0x%08x "
			       "word1=0x%08x word3=0x%08x\n",
			       first, (uint32_t)virt_to_phys(first),
			       first->len, first->addr,
			       first->word1, first->word3);
		}
		if (n_tx < 3) {
			uint32_t r = readl(p->base + EDMA_REG_TPD_IDX_Q(EDMA_TXQ_ID));
			/* Per-port MIB counters live at ess_base + 0x1000 +
			 * port*0x100; TX_BYTE is +0x10, TX_PKT is +0x18.
			 * Port 4 = LAN jack (gale port map). Port 0 = CPU port. */
			uint32_t p0_tx_byte = readl(p->esw + 0x1010);
			uint32_t p0_tx_pkt  = readl(p->esw + 0x1018);
			uint32_t p4_tx_byte = readl(p->esw + 0x1000 + 4*0x100 + 0x10);
			uint32_t p4_tx_pkt  = readl(p->esw + 0x1000 + 4*0x100 + 0x18);
			uint32_t p5_tx_byte = readl(p->esw + 0x1000 + 5*0x100 + 0x10);
			uint32_t p5_tx_pkt  = readl(p->esw + 0x1000 + 5*0x100 + 0x18);
			printf("ipq4019: TX #%d len=%d prod_after=0x%x cons_after=0x%x iters=%d\n",
			       n_tx + 1, length,
			       r & EDMA_TPD_PROD_IDX_MASK,
			       (r >> EDMA_TPD_CONS_IDX_SHIFT) & EDMA_TPD_CONS_IDX_MASK,
			       i);
			printf("ipq4019: MIB port0(CPU) tx_byte=%u tx_pkt=%u\n",
			       p0_tx_byte, p0_tx_pkt);
			printf("ipq4019: MIB port4(LAN) tx_byte=%u tx_pkt=%u\n",
			       p4_tx_byte, p4_tx_pkt);
			printf("ipq4019: MIB port5(WAN) tx_byte=%u tx_pkt=%u\n",
			       p5_tx_byte, p5_tx_pkt);
			n_tx++;
		}
	}
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
	static int link_logged;

	if (!p->started)
		ipq4019_eth_start(p);

	*ready = 0;
	for (i = 0; i < IPQ4019_NUM_PORT_PHY; i++) {
		uint16_t v = 0;
		ipq4019_mdio_read(i, QCA807X_PHY_SPECIFIC, &v);
		if (v & QCA807X_PHY_SPECIFIC_LINK) {
			*ready = 1;
			if (!link_logged) {
				/* QCA807X_PHY_SPECIFIC (0x11) bits:
				 *   [15:14] = speed (00=10M, 01=100M, 10=1000M)
				 *   [13] = duplex (1=full)
				 *   [10] = link up
				 */
				const char *spd = "??";
				switch ((v >> 14) & 3) {
				case 0: spd = "10M"; break;
				case 1: spd = "100M"; break;
				case 2: spd = "1G"; break;
				}
				printf("ipq4019: link up on PHY %d, %s/%s "
				       "(PHY_SPECIFIC=0x%04x)\n",
				       i, spd, (v & 0x2000) ? "full" : "half",
				       v);
				link_logged = 1;
			}
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

/*
 * ESS clock + block-reset (GCC pokes).
 *
 * Coreboot's gale build does NOT enable GCC_ESS_CLK (verified by grep across
 * coreboot/src/soc/qualcomm/ipq40xx/clock.c and coreboot/src/mainboard/google/
 * gale/ — only USB/UART/NAND/BLSP clocks are touched). Without the ESS clock
 * gated on, MDIO reads return 0x0000 for every PHY address: the MDIO state
 * machine has no clock to run.
 *
 * Mirror U-Boot's essedma_probe() ordering (clk_enable -> ess_reset):
 *   1. Enable GCC_ESS_CBCR (offset 0x12010, bit 0).
 *   2. Toggle GCC_ESS_BCR (offset 0x12008, bit 0): assert 10 ms, deassert 10 ms.
 *
 * Register offsets cross-checked against mainline Linux
 * drivers/clk/qcom/gcc-ipq4019.c. The BCR offset matches the existing
 * ess_reset() in ipq4019_psgmii.c (which is still called inside the PSGMII
 * calibration loop and serves the analog-SerDes-reset role there).
 */
#define IPQ4019_GCC_BASE		0x01800000
#define GCC_ESS_CBCR_OFFSET		0x12010
#define GCC_ESS_BCR_OFFSET		0x12008
#define GCC_ESS_CBCR_CLK_ENA		(1 << 0)
#define GCC_ESS_BCR_BLK_ARES		(1 << 0)

/*
 * IPQ4019 TLMM (pin mux) register layout (per coreboot soc/qualcomm/ipq40xx/
 * include/soc/iomap.h and gpio.h):
 *
 *   TLMM_BASE = 0x01000000
 *   Each GPIO has a 4-KiB control page at TLMM_BASE + (gpio * 0x1000):
 *     +0 GPIO_CFG  bits[1:0]=pull (0=NO,1=DOWN,2=UP), [5:2]=func (0=GPIO,
 *                                                                1=alt1...),
 *                   [8:6]=drive strength (0..7 -> 2..16 mA), [9]=output-enable.
 *     +4 GPIO_IN_OUT  bit[1]=output value (when OE=1); bit[0]=input value.
 *
 * Gale wiring (from OpenWrt qcom-ipq4019-wifi.dts, `mdio_pinmux` node):
 *   gpio6  -> function "mdio" (function index 1 in pinctrl-ipq4019.c)
 *   gpio7  -> function "mdc"  (function index 1)
 *   gpio40 -> GPIO output driven high (board-level QCA8075 enable/strap)
 *
 * Coreboot's gale board does NOT apply this pinmux — the production OpenWrt
 * kernel does via its DT pinctrl property. So the depthcharge driver MUST
 * apply it itself, or MDC/MDIO lines never leave the SoC and every PHY read
 * returns 0x0000 (the float reads as zero through the MDIO controller).
 */
#define IPQ4019_TLMM_BASE		0x01000000
#define TLMM_GPIO_CFG(n)		((void *)(IPQ4019_TLMM_BASE + 0x1000 * (n)))
#define TLMM_GPIO_IN_OUT(n)		((void *)(IPQ4019_TLMM_BASE + 0x1000 * (n) + 4))

/* GPIO_CFG fields (pull[1:0], func[5:2], drv[8:6], oe[9]). */
static uint32_t tlmm_cfg(uint32_t pull, uint32_t func,
			  uint32_t drv, uint32_t oe)
{
	return (pull & 0x3) | ((func & 0xf) << 2) | ((drv & 0x7) << 6)
	       | ((oe & 0x1) << 9);
}

static void ipq4019_mdio_pinmux_init(void)
{
	uint32_t cfg6_pre  = readl(TLMM_GPIO_CFG(6));
	uint32_t cfg7_pre  = readl(TLMM_GPIO_CFG(7));
	uint32_t cfg40_pre = readl(TLMM_GPIO_CFG(40));

	printf("ipq4019: TLMM pre-pinmux  gpio6=0x%08x gpio7=0x%08x gpio40=0x%08x\n",
	       cfg6_pre, cfg7_pre, cfg40_pre);

	/* gpio6 -> "mdio" (func 1), no pull, 8 mA, no GPIO-OE (peripheral
	 * controls direction). */
	writel(tlmm_cfg(0, 1, 3, 0), TLMM_GPIO_CFG(6));
	/* gpio7 -> "mdc" (func 1), no pull, 8 mA, no GPIO-OE. */
	writel(tlmm_cfg(0, 1, 3, 0), TLMM_GPIO_CFG(7));
	/* gpio40 -> GPIO function (0), output enabled, no pull, 8 mA. */
	writel(tlmm_cfg(0, 0, 3, 1), TLMM_GPIO_CFG(40));
	/* Drive gpio40 HIGH (output value at bit 1 of IN_OUT). */
	writel(1 << 1, TLMM_GPIO_IN_OUT(40));

	printf("ipq4019: TLMM post-pinmux gpio6=0x%08x gpio7=0x%08x gpio40=0x%08x out40=0x%08x\n",
	       readl(TLMM_GPIO_CFG(6)), readl(TLMM_GPIO_CFG(7)),
	       readl(TLMM_GPIO_CFG(40)), readl(TLMM_GPIO_IN_OUT(40)));
}

/*
 * Per-port async reset bits live at GCC offset 0x1200C:
 *   bit 0 = GCC_ESS_MAC1_ARES,  bit 1 = MAC2_ARES,
 *   bit 2 = MAC3_ARES,          bit 3 = MAC4_ARES,
 *   bit 4 = MAC5_ARES,          bit 5 = GCC_ESS_PSGMII_ARES.
 * Per mainline Linux drivers/clk/qcom/gcc-ipq4019.c lines 1690-1695.
 * If any of these are stuck asserted, the corresponding MAC/PSGMII PHY
 * won't respond to MDIO.
 */
#define GCC_ESS_PORT_ARES_OFFSET		0x1200C

static void ipq4019_ess_clock_and_reset_init(void)
{
	void *cbcr = (void *)(IPQ4019_GCC_BASE + GCC_ESS_CBCR_OFFSET);
	void *bcr  = (void *)(IPQ4019_GCC_BASE + GCC_ESS_BCR_OFFSET);
	void *pares = (void *)(IPQ4019_GCC_BASE + GCC_ESS_PORT_ARES_OFFSET);
	uint32_t v;

	printf("ipq4019: GCC_ESS_CBCR pre-enable    = 0x%08x\n", readl(cbcr));
	printf("ipq4019: GCC_ESS_BCR  pre-toggle    = 0x%08x\n", readl(bcr));
	printf("ipq4019: GCC_ESS_PORT_ARES initial   = 0x%08x\n", readl(pares));

	v = readl(cbcr);
	writel(v | GCC_ESS_CBCR_CLK_ENA, cbcr);
	mdelay(10);
	printf("ipq4019: GCC_ESS_CBCR post-enable   = 0x%08x\n", readl(cbcr));

	/* BCR is a 1-bit reset toggle. */
	writel(GCC_ESS_BCR_BLK_ARES, bcr);
	mdelay(10);
	writel(0, bcr);
	mdelay(10);
	printf("ipq4019: GCC_ESS_BCR  post-toggle   = 0x%08x\n", readl(bcr));

	/* Clear any stuck per-port resets (MAC1..5 + PSGMII = bits 0..5).
	 * Mask-clear only the known ARES bits — leave any other bits in the
	 * register untouched (defensive against undocumented bits >5). */
	v = readl(pares);
	if (v & 0x3F) {
		printf("ipq4019: clearing per-port resets, was 0x%08x\n", v);
		writel(v & ~0x3F, pares);
		mdelay(10);
	}
	printf("ipq4019: GCC_ESS_PORT_ARES final    = 0x%08x\n", readl(pares));
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

	ipq4019_mdio_pinmux_init();
	printf("ipq4019: MDIO pinmux initialized\n");

	ipq4019_ess_clock_and_reset_init();
	printf("ipq4019: ESS clock+reset initialized\n");

	ipq4019_mdio_init();

	/* v15: SKIP PSGMII calibration entirely. Each qca8075_ess_reset
	 * BCR-toggles the WHOLE ESS block, which resets switch + EDMA +
	 * MDIO state we'd then have to redo. Test whether PBL leaves the
	 * SerDes in a usable state. */
	printf("ipq4019: PSGMII cal SKIPPED (static config test)\n");

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
 * report "no link" — the driver halts cleanly instead of looping forever.
 *
 * This is good engineering hygiene (fast iteration, clear failure mode),
 * not a SuzyQ-recovery mechanism. SuzyQ re-flash works regardless via
 * `gale power off` + the documented procedure (see
 * docs/keeping-suzyq-recovery-working.md). Bounded retries just make
 * the failure state quiet rather than chatty.
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
		       "(driver halted)\n", retry_count);
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

/*
 * Copyright 2026 Google LLC / contributors.
 *
 * IPQ4019 (Google Wifi "gale") ESS EDMA ethernet driver for depthcharge.
 *
 * Register map and descriptor layout ported from the mainline U-Boot
 * driver drivers/net/essedma.{c,h} (GPL-2.0+, Robert Marko / Gabor Juhos,
 * Sartura) and cross-checked against the Linux IPQESS driver.
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; either version 2 of
 * the License, or (at your option) any later version.
 */

#ifndef __DRIVERS_NET_IPQ4019_H__
#define __DRIVERS_NET_IPQ4019_H__

#include <stdint.h>

/* --- SoC block base addresses (gale / IPQ4019; see docs/hardware.md) --- */
#define IPQ4019_EDMA_BASE	0x0c080000	/* ESS EDMA registers (0x8000) */
#define IPQ4019_ESS_BASE	0x0c000000	/* switch "base" (0x80000)     */
#define IPQ4019_PSGMII_BASE	0x00098000	/* PSGMII PHY calibration      */
#define IPQ4019_MDIO_BASE	0x00090000	/* MDIO controller             */
#define RGMII_TCSR_ESS_CFG	0x01953000

/* --- MDIO controller (offsets from IPQ4019_MDIO_BASE) --- */
#define MDIO_MODE_REG		0x40
#define MDIO_ADDR_REG		0x44
#define MDIO_DATA_WRITE_REG	0x48
#define MDIO_DATA_READ_REG	0x4c
#define MDIO_CMD_REG		0x50
#define MDIO_CMD_ACCESS_BUSY	(1 << 16)
#define MDIO_CMD_ACCESS_START	(1 << 8)
#define MDIO_CMD_ACCESS_CODE_READ	0
#define MDIO_CMD_ACCESS_CODE_WRITE	1
#define MDIO_MODE_C45		(1 << 8)	/* 0 = clause 22 */

/* --- ESS switch registers (offsets from IPQ4019_ESS_BASE) --- */
#define ESS_PORTS_NUM			6
#define ESS_RGMII_CTRL			0x4
#define ESS_GLOBAL_FW_CTRL1		0x624
#define ESS_PORT0_STATUS		0x7c
#define ESS_PORT_SPEED_MASK		0x3
#define ESS_PORT_SPEED_1000		3
#define ESS_PORT_SPEED_100		2
#define ESS_PORT_SPEED_10		1
#define ESS_PORT_TXMAC_EN		(1 << 2)
#define ESS_PORT_RXMAC_EN		(1 << 3)
#define ESS_PORT_TX_FLOW_EN		(1 << 4)
#define ESS_PORT_RX_FLOW_EN		(1 << 5)
#define ESS_PORT_DUPLEX_MODE		(1 << 6)
#define ESS_PORT_LOOKUP_CTRL(_p)	(0x660 + (_p) * 12)
#define ESS_PORT_LOOP_BACK_EN		(1 << 21)
#define ESS_PORT_VID_MEM_MASK		0x7f	/* bits [6:0] */
#define ESS_PORT_HOL_CTRL0(_p)		(0x970 + (_p) * 8)
#define ESS_PORT_HOL_CTRL1(_p)		(0x974 + (_p) * 8)
#define ESS_ING_BUF_NUM_0_MASK		0xf	/* bits [3:0] */
/* HOL_CTRL0 sub-fields (shifts) */
#define EG_PORT_QUEUE_NUM_SHIFT		24	/* bits [29:24] */
#define EG_PRI5_QUEUE_NUM_SHIFT		20
#define EG_PRI4_QUEUE_NUM_SHIFT		16
#define EG_PRI3_QUEUE_NUM_SHIFT		12
#define EG_PRI2_QUEUE_NUM_SHIFT		8
#define EG_PRI1_QUEUE_NUM_SHIFT		4
#define EG_PRI0_QUEUE_NUM_SHIFT		0

/* --- QCA807x PHY registers (clause 22 + MMD) --- */
#define QCA807X_CHIP_CONFIGURATION		0x1f
#define QCA807X_MEDIA_PAGE_SELECT		(1 << 15)
#define QCA807X_POWER_DOWN			(1 << 11)
#define QCA807X_FUNCTION_CONTROL		0x10
#define QCA807X_MDI_CROSSOVER_MODE_MASK		(3 << 5)	/* bits [6:5] */
#define QCA807X_MDI_CROSSOVER_MODE_MANUAL_MDI	0
#define QCA807X_POLARITY_REVERSAL		(1 << 1)
#define QCA807X_PHY_SPECIFIC			0x11
#define QCA807X_PHY_SPECIFIC_LINK		(1 << 10)
#define QCA807X_MMD7_CRC_PACKET_COUNTER		0x8029
#define QCA807X_MMD7_PACKET_COUNTER_SELFCLR	(1 << 1)
#define QCA807X_MMD7_CRC_PACKET_COUNTER_EN	(1 << 0)
#define QCA807X_MMD7_VALID_EGRESS_COUNTER_2	0x802e

/* MMD device addresses */
#define MDIO_MMD_PMAPMD		1
#define MDIO_MMD_AN		7

/* standard clause-22 regs */
#define MII_BMCR		0x00

/* --- PSGMII calibration registers (offsets from IPQ4019_PSGMII_BASE) --- */
#define PSGMIIPHY_VCO_CALIBRATION_CTRL_REGISTER_1	0x9c
#define PSGMIIPHY_VCO_VAL				0x4ada
#define PSGMIIPHY_VCO_RST_VAL				0x0ada
#define PSGMIIPHY_VCO_CALIBRATION_CTRL_REGISTER_2	0xa0
#define PSGMIIPHY_PLL_VCO_RELATED_CTRL			0x78c
#define PSGMIIPHY_PLL_VCO_VAL				0x2803

/* --- EDMA registers (offsets from IPQ4019_EDMA_BASE) --- */
#define IPQ4019_EDMA_TX_RING_SIZE	8
#define IPQ4019_EDMA_RSS_TYPE_NONE	0x1
#define EDMA_TPD_EOP_SHIFT		31
#define EDMA_TPD_PORT_BITMAP_SHIFT	18
#define EDMA_PORT_ENABLE_ALL		0x3E

#define EDMA_REG_RX_SW_CONS_IDX_Q(x)	(0x220 + ((x) << 2))
#define EDMA_REG_TX_SW_CONS_IDX_Q(x)	(0x240 + ((x) << 2))
#define EDMA_REG_TPD_IDX_Q(x)		(0x460 + ((x) << 2))
#define EDMA_REG_TPD_RING_SIZE		0x41C
#define EDMA_TPD_RING_SIZE_MASK		0xFFFF
#define EDMA_REG_TPD_BASE_ADDR_Q(x)	(0x420 + ((x) << 2))
#define EDMA_TPD_PROD_IDX_MASK		0xFFFF		/* bits [15:0]  */
#define EDMA_TPD_CONS_IDX_SHIFT		16		/* bits [31:16] */
#define EDMA_TPD_CONS_IDX_MASK		0xFFFF
#define EDMA_REG_TX_SRAM_PART		0x400
#define EDMA_LOAD_PTR_SHIFT		16
#define EDMA_REG_TXQ_CTRL		0x404
#define EDMA_TXQ_CTRL_TXQ_EN		0x20
#define EDMA_TXQ_CTRL_TPD_BURST_EN	0x100
#define EDMA_TXQ_NUM_TPD_BURST_SHIFT	0
#define EDMA_TXQ_TXF_BURST_NUM_SHIFT	16
#define EDMA_TXF_BURST			0x100
#define EDMA_TPD_BURST			5
#define EDMA_REG_TXF_WATER_MARK		0x408
#define EDMA_REG_RSS_TYPE		0x894
#define EDMA_REG_RFD_BASE_ADDR_Q(x)	(0x950 + ((x) << 2))
#define EDMA_RFD_BURST			8
#define EDMA_RFD_THR			16
#define EDMA_RFD_LTHR			0
#define EDMA_REG_RFD_IDX_Q(x)		(0x9B0 + ((x) << 2))
#define EDMA_RFD_CONS_IDX_SHIFT		16		/* bits [27:16] */
#define EDMA_RFD_CONS_IDX_MASK		0xFFF
#define EDMA_REG_RX_DESC0		0xA10
#define EDMA_RFD_RING_SIZE_MASK		0xFFF
#define EDMA_RX_BUF_SIZE_MASK		0xFFFF
#define EDMA_RFD_RING_SIZE_SHIFT	0
#define EDMA_RX_BUF_SIZE_SHIFT		16
#define EDMA_REG_RX_DESC1		0xA14
#define EDMA_RXQ_RFD_BURST_NUM_SHIFT	0
#define EDMA_RXQ_RFD_PF_THRESH_SHIFT	8
#define EDMA_RXQ_RFD_LOW_THRESH_SHIFT	16
#define EDMA_REG_RXQ_CTRL		0xA18
#define EDMA_FIFO_THRESH_128_BYTE	0x0
#define EDMA_RXQ_CTRL_RMV_VLAN		0x00000002
#define EDMA_RXQ_CTRL_EN		0x0000FF00
#define REG_MAC_CTRL0			0xC20
#define REG_MAC_CTRL1			0xC24

/* RSS indirection (disabled but must be written) */
#define EDMA_REG_RSS_IDT(x)		(0x840 + ((x) << 2))
#define EDMA_NUM_IDT			16
#define EDMA_RSS_IDT_VALUE		0x64206420

/* --- descriptors --- */
typedef struct {
	uint16_t len;		/* full packet including CRC */
	uint16_t svlan_tag;
	uint32_t word1;		/* EOP = 1<<31 */
	uint32_t addr;		/* buffer phys addr */
	uint32_t word3;		/* port bitmap << 18 */
} edma_tpd;			/* transmit packet descriptor (16 bytes) */

typedef struct {
	uint16_t rrd0;
	uint16_t rrd1;
	uint16_t rrd2;
	uint16_t rrd3;
	uint16_t rrd4;
	uint16_t rrd5;
	uint16_t rrd6;		/* packet length */
	uint16_t rrd7;		/* bit 15 = descriptor valid */
} __attribute__((packed)) edma_rrd;	/* receive return descriptor */

#define EDMA_RRD_SIZE		(sizeof(edma_rrd))
#define EDMA_RRD7_DESC_VALID	(1 << 15)

typedef struct {
	uint32_t buffer_addr;	/* rx buffer phys addr */
} edma_rfd;			/* receive free descriptor */

/* PHY topology (QCA8075): 5 port PHYs at MDIO 0..4, PSGMII PHY at 5 */
#define IPQ4019_PHY_PSGMII_ADDR	5
#define IPQ4019_NUM_PORT_PHY	5

/* MDIO helpers (ipq4019_mdio.c) */
int ipq4019_mdio_read(uint8_t phy, uint8_t reg, uint16_t *val);
int ipq4019_mdio_write(uint8_t phy, uint8_t reg, uint16_t val);
uint16_t ipq4019_phy_read_mmd(uint8_t phy, uint8_t devad, uint16_t reg);
void ipq4019_phy_write_mmd(uint8_t phy, uint8_t devad, uint16_t reg, uint16_t val);
void ipq4019_mdio_init(void);

/* PSGMII calibration (ipq4019_psgmii.c). Returns 0 on success, -1 on
 * convergence failure (caller may retry by calling eth_init again). */
int ipq4019_psgmii_self_test(void);

#endif /* __DRIVERS_NET_IPQ4019_H__ */

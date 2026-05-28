/*
 * Copyright 2026 Google LLC / contributors.
 *
 * IPQ4019 QCA8075 PSGMII calibration / self-test for depthcharge.
 * Ported faithfully from mainline U-Boot drivers/net/essedma.c (GPL-2.0+,
 * Robert Marko / Gabor Juhos, Sartura). phylib calls replaced with the local
 * clause-22/MMD MDIO helpers; the PHYs are plain MDIO addresses (0..4 port
 * PHYs, 5 = PSGMII). The PSGMII SerDes MUST be calibrated or links are flaky.
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; either version 2 of
 * the License, or (at your option) any later version.
 */

#include <libpayload.h>

#include "drivers/net/ipq4019.h"

/*
 * ESS block reset via GCC. IPQ4019 GCC base = 0x1800000.
 *
 * GCC_ESS_BCR offset confirmed from the upstream Linux IPQ4019 GCC driver
 * (drivers/clk/qcom/gcc-ipq4019.c):
 *
 *     [GCC_ESS_BCR] = { 0x12008, 0 },
 *
 * where the second 0 indicates bit 0 — the standard Qualcomm BCR BLK_ARES
 * assertion bit. (The same offset also appears as [ESS_RESET] in that file.)
 */
#define IPQ4019_GCC_BASE	0x01800000
#define GCC_ESS_BCR		0x12008
#define GCC_ESS_BCR_BLK_ARES	(1 << 0)

static void *const ess = (void *)IPQ4019_ESS_BASE;
static void *const psgmii = (void *)IPQ4019_PSGMII_BASE;

/* The PSGMII PHY is the calibration interface (MDIO addr 5). */
static const uint8_t psgmii_phy = IPQ4019_PHY_PSGMII_ADDR;

static void ess_reset(void)
{
	void *bcr = (void *)(IPQ4019_GCC_BASE + GCC_ESS_BCR);

	writel(GCC_ESS_BCR_BLK_ARES, bcr);
	mdelay(10);
	writel(0, bcr);
	mdelay(10);
}

static void esw_port_loopback_set(int port, int enable)
{
	uint32_t t = readl(ess + ESS_PORT_LOOKUP_CTRL(port));

	if (enable)
		t |= ESS_PORT_LOOP_BACK_EN;
	else
		t &= ~ESS_PORT_LOOP_BACK_EN;
	writel(t, ess + ESS_PORT_LOOKUP_CTRL(port));
}

static void esw_port_loopback_set_all(int enable)
{
	int i;

	for (i = 1; i < ESS_PORTS_NUM; i++)
		esw_port_loopback_set(i, enable);
}

/* QCA8075 PSGMII reset/CDR dance + PLL VCO calibration handshake. */
static void qca8075_ess_reset(void)
{
	int i, val;

	/* Fix phy psgmii RX 20bit */
	ipq4019_mdio_write(psgmii_phy, MII_BMCR, 0x005b);
	/* Reset phy psgmii */
	ipq4019_mdio_write(psgmii_phy, MII_BMCR, 0x001b);
	/* Release reset phy psgmii */
	ipq4019_mdio_write(psgmii_phy, MII_BMCR, 0x005b);

	for (i = 0; i < 100; i++) {
		val = ipq4019_phy_read_mmd(psgmii_phy, MDIO_MMD_PMAPMD, 0x28);
		if (val & 0x1)
			break;
		mdelay(1);
	}
	if (i >= 100)
		printf("ipq4019: QCA807x PSGMII PLL_VCO_CALIB Not Ready\n");

	/* Freeze phy psgmii RX CDR */
	ipq4019_mdio_write(psgmii_phy, 0x1a, 0x2230);

	ess_reset();

	/* Check ipq psgmii calibration done */
	for (i = 0; i < 100; i++) {
		val = readl(psgmii + PSGMIIPHY_VCO_CALIBRATION_CTRL_REGISTER_2);
		if (val & 0x1)
			break;
		mdelay(1);
	}
	if (i >= 100)
		printf("ipq4019: PSGMII PLL_VCO_CALIB Not Ready\n");

	/* Release phy psgmii RX CDR */
	ipq4019_mdio_write(psgmii_phy, 0x1a, 0x3230);
	/* Release phy psgmii RX 20bit */
	ipq4019_mdio_write(psgmii_phy, MII_BMCR, 0x005f);
}

#define PSGMII_ST_NUM_RETRIES	20
#define PSGMII_ST_PKT_COUNT	(4 * 1024)
#define PSGMII_ST_PKT_SIZE	1504

static void psgmii_st_phy_power_down(uint8_t phy)
{
	uint16_t val = 0;

	ipq4019_mdio_read(phy, MII_BMCR, &val);
	val |= QCA807X_POWER_DOWN;
	ipq4019_mdio_write(phy, MII_BMCR, val);
}

static void psgmii_st_phy_prepare(uint8_t phy)
{
	uint16_t val = 0;

	ipq4019_mdio_read(phy, QCA807X_CHIP_CONFIGURATION, &val);
	if (val) {
		val |= QCA807X_MEDIA_PAGE_SELECT;
		ipq4019_mdio_write(phy, QCA807X_CHIP_CONFIGURATION, val);
	}

	psgmii_st_phy_power_down(phy);

	ipq4019_phy_write_mmd(phy, MDIO_MMD_AN, 0x8021, PSGMII_ST_PKT_COUNT);
	ipq4019_phy_write_mmd(phy, MDIO_MMD_AN, 0x8062, PSGMII_ST_PKT_SIZE);

	ipq4019_mdio_read(phy, QCA807X_FUNCTION_CONTROL, &val);
	val &= ~QCA807X_MDI_CROSSOVER_MODE_MASK;	/* MANUAL_MDI = 0 */
	val &= ~QCA807X_POLARITY_REVERSAL;
	ipq4019_mdio_write(phy, QCA807X_FUNCTION_CONTROL, val);
}

static void psgmii_st_phy_recover(uint8_t phy)
{
	uint16_t val;

	ipq4019_phy_write_mmd(phy, MDIO_MMD_AN, 0x8021, 0x0);
	val = ipq4019_phy_read_mmd(phy, MDIO_MMD_AN, QCA807X_MMD7_CRC_PACKET_COUNTER);
	val &= ~QCA807X_MMD7_PACKET_COUNTER_SELFCLR;
	val &= ~QCA807X_MMD7_CRC_PACKET_COUNTER_EN;
	ipq4019_phy_write_mmd(phy, MDIO_MMD_AN, QCA807X_MMD7_CRC_PACKET_COUNTER, val);
	ipq4019_phy_write_mmd(phy, MDIO_MMD_AN, 0x8020, 0x0);
}

static void psgmii_st_phy_start_traffic(uint8_t phy)
{
	uint16_t val = ipq4019_phy_read_mmd(phy, MDIO_MMD_AN,
					    QCA807X_MMD7_CRC_PACKET_COUNTER);
	val |= QCA807X_MMD7_CRC_PACKET_COUNTER_EN;
	ipq4019_phy_write_mmd(phy, MDIO_MMD_AN, QCA807X_MMD7_CRC_PACKET_COUNTER, val);
	ipq4019_phy_write_mmd(phy, MDIO_MMD_AN, 0x8020, 0xa000);
}

static int psgmii_st_phy_check_counters(uint8_t phy)
{
	uint16_t tx_ok = ipq4019_phy_read_mmd(phy, MDIO_MMD_AN,
					      QCA807X_MMD7_VALID_EGRESS_COUNTER_2);
	return tx_ok == (PSGMII_ST_PKT_COUNT & 0xffff);
}

static void psgmii_st_phy_reset_loopback(uint8_t phy)
{
	ipq4019_mdio_write(phy, MII_BMCR, 0x9000);	/* reset */
	ipq4019_mdio_write(phy, MII_BMCR, 0x4140);	/* loopback */
}

static int psgmii_st_phy_link_is_up(uint8_t phy)
{
	uint16_t val = 0;

	ipq4019_mdio_read(phy, QCA807X_PHY_SPECIFIC, &val);
	return !!(val & QCA807X_PHY_SPECIFIC_LINK);
}

static int psgmii_st_phy_wait(uint32_t mask, int retries, int delay,
			      int (*check)(uint8_t))
{
	int i, phy;

	for (i = 0; i < retries; i++) {
		for (phy = 0; phy < IPQ4019_NUM_PORT_PHY; phy++) {
			uint32_t bit = 1 << phy;
			if (!(mask & bit))
				continue;
			if (check(phy))
				mask &= ~bit;
		}
		if (!mask)
			break;
		mdelay(delay);
	}
	return mask == 0;
}

static int psgmii_st_run_test_serial(uint32_t phy_mask)
{
	int i, result = 1;

	for (i = 0; i < IPQ4019_NUM_PORT_PHY; i++) {
		psgmii_st_phy_reset_loopback(i);
		psgmii_st_phy_wait(1 << i, 100, 10, psgmii_st_phy_link_is_up);
		psgmii_st_phy_start_traffic(i);
		result &= psgmii_st_phy_wait(1 << i, 5000, 1,
					     psgmii_st_phy_check_counters);
		psgmii_st_phy_power_down(i);
		if (!result)
			break;
	}
	return result;
}

static int psgmii_st_run_test_parallel(uint32_t phy_mask)
{
	int i, result;

	for (i = 0; i < IPQ4019_NUM_PORT_PHY; i++)
		psgmii_st_phy_reset_loopback(i);
	psgmii_st_phy_wait(phy_mask, 100, 10, psgmii_st_phy_link_is_up);
	for (i = 0; i < IPQ4019_NUM_PORT_PHY; i++)
		psgmii_st_phy_start_traffic(i);
	result = psgmii_st_phy_wait(phy_mask, 5000, 1, psgmii_st_phy_check_counters);
	for (i = 0; i < IPQ4019_NUM_PORT_PHY; i++)
		psgmii_st_phy_power_down(i);
	return result;
}

void ipq4019_psgmii_self_test(void)
{
	uint32_t phy_mask = (1 << IPQ4019_NUM_PORT_PHY) - 1;
	int i, result = 0;

	/* PSGMII analog VCO/PLL calibration writes (PSGMII interface mode). */
	writel(PSGMIIPHY_PLL_VCO_VAL, psgmii + PSGMIIPHY_PLL_VCO_RELATED_CTRL);
	writel(PSGMIIPHY_VCO_VAL, psgmii + PSGMIIPHY_VCO_CALIBRATION_CTRL_REGISTER_1);
	mdelay(10);
	writel(PSGMIIPHY_VCO_RST_VAL, psgmii + PSGMIIPHY_VCO_CALIBRATION_CTRL_REGISTER_1);

	for (i = 0; i < IPQ4019_NUM_PORT_PHY; i++)
		psgmii_st_phy_prepare(i);

	for (i = 0; i < PSGMII_ST_NUM_RETRIES; i++) {
		qca8075_ess_reset();
		esw_port_loopback_set_all(1);
		result = psgmii_st_run_test_serial(phy_mask);
		if (result)
			result = psgmii_st_run_test_parallel(phy_mask);
		if (result)
			break;
	}
	if (!result)
		printf("ipq4019: PSGMII self-test did not converge after %d tries\n",
		       PSGMII_ST_NUM_RETRIES);
	else
		printf("ipq4019: PSGMII self-test passed (try %d)\n", i + 1);

	/* recover PHYs + disable loopback */
	for (i = 0; i < IPQ4019_NUM_PORT_PHY; i++) {
		psgmii_st_phy_recover(i);
		ipq4019_mdio_write(i, QCA807X_FUNCTION_CONTROL, 0x6860);
		ipq4019_mdio_write(i, MII_BMCR, 0x9040);
	}
	esw_port_loopback_set_all(0);
}

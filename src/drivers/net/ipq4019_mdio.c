/*
 * Copyright 2026 Google LLC / contributors.
 *
 * IPQ4019 MDIO (clause-22) + MMD (clause-45-indirect) helpers for depthcharge.
 * Ported from mainline U-Boot drivers/net/mdio-ipq4019.c (GPL-2.0+,
 * Luka Kovacic / Robert Marko, Sartura) with the driver-model wrapper removed
 * and the register base hardcoded for gale.
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; either version 2 of
 * the License, or (at your option) any later version.
 */

#include <libpayload.h>

#include "drivers/net/ipq4019.h"

#define MDIO_BUSY_TIMEOUT_US	100000	/* generous */
#define MDIO_POLL_US		10

static void *mdio_base = (void *)IPQ4019_MDIO_BASE;

static int mdio_wait_busy(void)
{
	int i;

	for (i = 0; i < MDIO_BUSY_TIMEOUT_US / MDIO_POLL_US; i++) {
		if (!(readl(mdio_base + MDIO_CMD_REG) & MDIO_CMD_ACCESS_BUSY))
			return 0;
		udelay(MDIO_POLL_US);
	}
	printf("ipq4019_mdio: busy timeout\n");
	return -1;
}

int ipq4019_mdio_read(uint8_t phy, uint8_t reg, uint16_t *val)
{
	if (mdio_wait_busy())
		return -1;

	writel((phy << 8) | reg, mdio_base + MDIO_ADDR_REG);
	writel(MDIO_CMD_ACCESS_START | MDIO_CMD_ACCESS_CODE_READ,
	       mdio_base + MDIO_CMD_REG);

	if (mdio_wait_busy())
		return -1;

	*val = readl(mdio_base + MDIO_DATA_READ_REG) & 0xffff;
	return 0;
}

int ipq4019_mdio_write(uint8_t phy, uint8_t reg, uint16_t val)
{
	if (mdio_wait_busy())
		return -1;

	writel((phy << 8) | reg, mdio_base + MDIO_ADDR_REG);
	writel(val, mdio_base + MDIO_DATA_WRITE_REG);
	writel(MDIO_CMD_ACCESS_START | MDIO_CMD_ACCESS_CODE_WRITE,
	       mdio_base + MDIO_CMD_REG);

	return mdio_wait_busy();
}

/*
 * Clause-45 "MMD" access tunnelled over clause-22, via the standard
 * registers 0x0d (MMD access control) and 0x0e (MMD access data).
 * ctrl function field: 0=address, 0x4000=data (no post-increment).
 */
#define MII_MMD_CTRL	0x0d
#define MII_MMD_DATA	0x0e
#define MMD_CTRL_DATA	0x4000

uint16_t ipq4019_phy_read_mmd(uint8_t phy, uint8_t devad, uint16_t reg)
{
	uint16_t v = 0;

	ipq4019_mdio_write(phy, MII_MMD_CTRL, devad);
	ipq4019_mdio_write(phy, MII_MMD_DATA, reg);
	ipq4019_mdio_write(phy, MII_MMD_CTRL, MMD_CTRL_DATA | devad);
	ipq4019_mdio_read(phy, MII_MMD_DATA, &v);
	return v;
}

void ipq4019_phy_write_mmd(uint8_t phy, uint8_t devad, uint16_t reg, uint16_t val)
{
	ipq4019_mdio_write(phy, MII_MMD_CTRL, devad);
	ipq4019_mdio_write(phy, MII_MMD_DATA, reg);
	ipq4019_mdio_write(phy, MII_MMD_CTRL, MMD_CTRL_DATA | devad);
	ipq4019_mdio_write(phy, MII_MMD_DATA, val);
}

void ipq4019_mdio_init(void)
{
	uint32_t mode_pre = readl(mdio_base + MDIO_MODE_REG);
	uint32_t cmd_pre  = readl(mdio_base + MDIO_CMD_REG);
	uint32_t mode_post;

	printf("ipq4019_mdio: MDIO_MODE pre  = 0x%08x  CMD pre  = 0x%08x\n",
	       mode_pre, cmd_pre);

	/* Force clause-22 by clearing the C45 bit. */
	writel(mode_pre & ~MDIO_MODE_C45, mdio_base + MDIO_MODE_REG);
	mode_post = readl(mdio_base + MDIO_MODE_REG);

	printf("ipq4019_mdio: MDIO_MODE post = 0x%08x  (writeback %s)\n",
	       mode_post,
	       (mode_post == (mode_pre & ~MDIO_MODE_C45)) ? "MATCHES" :
	       (mode_post == 0xffffffff) ? "all-1s (bus fault?)" :
	       (mode_post == 0) ? "all-0s (controller dead?)" : "MISMATCH");

	/* Probe MDIO_ADDR_REG roundtrip as another liveness check. */
	writel(0x1234, mdio_base + MDIO_ADDR_REG);
	uint32_t addr_back = readl(mdio_base + MDIO_ADDR_REG);
	printf("ipq4019_mdio: MDIO_ADDR write=0x1234 read=0x%08x  %s\n",
	       addr_back, (addr_back == 0x1234) ? "MATCHES" : "MISMATCH");
}

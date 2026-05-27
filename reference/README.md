<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Vendored reference sources

These files are **unmodified copies** of upstream code, included for the
implementer's convenience. They are all GPL-2.0-or-later, the same license as
this repository, so vendoring is license-clean. Do **not** edit them — they are
read-only references. The driver written for this project is a *derivative work*
of these files.

| File here | Upstream | Commit | License |
|-----------|----------|--------|---------|
| `uboot-essedma.c` | u-boot `drivers/net/essedma.c` | `987907ae4bcc` | GPL-2.0+ |
| `uboot-essedma.h` | u-boot `drivers/net/essedma.h` | `987907ae4bcc` | GPL-2.0+ |
| `uboot-mdio-ipq4019.c` | u-boot `drivers/net/mdio-ipq4019.c` | `987907ae4bcc` | GPL-2.0+ |
| `depthcharge-ipq806x.c` | depthcharge `src/drivers/net/ipq806x.c` @ `firmware-gale-8281.B` | `b88cbbe1bb16` | GPL-2.0+ |
| `depthcharge-net.h` | depthcharge `src/drivers/net/net.h` @ `firmware-gale-8281.B` | `b88cbbe1bb16` | GPL-2.0+ |

## What each is for

- **`uboot-essedma.c` / `.h`** — the *primary register-level reference*. Mainline
  U-Boot's IPQ40xx ESS EDMA driver (authors Robert Marko / Gabor Juhos, Sartura).
  Bare-metal and **polled** (no IRQ/NAPI), exactly depthcharge's model. Contains
  the full bring-up: QCA8075 PSGMII calibration/self-test, ESS switch init, EDMA
  ring setup, and polled `send`/`recv`.
- **`uboot-mdio-ipq4019.c`** — the IPQ4019 MDIO access (clause-22) the PHY/PSGMII
  code needs. Trivially portable (register pokes at MDIO base + 0x40..0x50).
- **`depthcharge-ipq806x.c`** — the *structural* template: how a Qualcomm NIC plugs
  into depthcharge (`INIT_FUNC`→`NetPoller`→lazy init→`net_add_device`), coreboot
  MAC handling (`lib_sysinfo.macs[0]`), and ARM cache-coherent DMA. Its *registers*
  are wrong for IPQ4019 (DesignWare GMAC) — only the shape transfers.
- **`depthcharge-net.h`** — the `NetDevice` interface contract the new driver must
  implement.

A third reference (not vendored, fetch as needed): the Linux IPQESS driver in
OpenWrt, `target/linux/ipq40xx/patches-*/700-net-ipqess-introduce-the-Qualcomm-IPQESS-driver.patch`
(openwrt commit `028dc3f57a6f`). Useful to cross-check register semantics.

<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# References & provenance

All sources below were read on 2026-05-28 and pinned to the commits shown.

## Target

- **Device**: Google Wifi, board codename **`gale`**, SoC **Qualcomm IPQ4019**
  (ARMv7 Cortex-A7 quad-core, "Dakota"/IPQ40xx family).
- **Firmware on device**: 8 MiB Winbond W25Q64 SPI-NOR. coreboot RO + depthcharge
  payload in `RW_SECTION_A/B`. eMMC holds kernel/rootfs only.
- **Debug access**: SuzyQ cable → 2× `/dev/ttyUSB` (AP + EC consoles), EC-mediated
  (no Cr50). Serial console is the primary bring-up instrument.

## depthcharge (the payload we are modifying)

- Repo: `https://chromium.googlesource.com/chromiumos/platform/depthcharge`
- Branch: **`firmware-gale-8281.B`** (matches the coreboot branch shipping on gale)
- Commit: `b88cbbe1bb16343be5076d8b81108815fff5ff45`
- Key paths:
  - `src/drivers/net/net.h` — `NetDevice` interface (the contract to implement)
  - `src/drivers/net/net.c` — framework: `net_add_device`, `net_wait_for_link`, `net_poll`
  - `src/drivers/net/ipq806x.c` — **structural template** (IPQ806x DesignWare GMAC)
  - `src/drivers/net/Kconfig`, `src/drivers/net/Makefile.inc` — driver registration
  - `src/board/gale/board.c`, `board/gale/defconfig` — the board (no net driver today)
  - `src/board/storm/board.c`, `board/storm/defconfig` — how a board enables a net driver
  - `src/netboot/netboot.c` — netboot flow (DHCP→TFTP→boot)
  - `src/Makefile.inc` — `netboot` and `dev` images link `net-objs`

## U-Boot (primary register-level reference)

- Repo: `https://github.com/u-boot/u-boot` (mainline), commit `987907ae4bcc5d6055bdf7d318a3edf53e14d5fa`
- Files: `drivers/net/essedma.c`, `drivers/net/essedma.h`, `drivers/net/mdio-ipq4019.c`
- Kconfig: `CONFIG_ESSEDMA` (depends on `DM_ETH && ARCH_IPQ40XX`), `CONFIG_MDIO_IPQ4019`
- Authors: Robert Marko (Sartura), Gabor Juhos, Luka Kovacic. License GPL-2.0+.
- Why primary: bare-metal, **polled**, no interrupts/NAPI — the same execution
  model depthcharge uses. The whole IPQ4019 bring-up (PSGMII calibration, switch
  init, EDMA rings) is present in a form that maps almost 1:1 onto `NetDevice`.

## Linux (cross-check reference)

- OpenWrt `https://github.com/openwrt/openwrt`, commit `028dc3f57a6f9430181587a5af34d0cb7e9a442e`
- `target/linux/ipq40xx/patches-6.18/700-net-ipqess-introduce-the-Qualcomm-IPQESS-driver.patch`
  — the IPQESS (DSA) driver; authoritative register semantics.
- DT addresses confirmed from `705-ARM-dts-qcom-ipq4019-Add-description-for-the-IPQESS-.patch`
  and `707-arm-dts-ipq4019-add-switch-node.patch`.
- Historic alternative: the classic `essedma` + `ar40xx.c` (non-DSA) driver.

## Licensing

depthcharge files carry "GPL ... version 2 ... or (at your option) any later
version"; U-Boot `essedma.*` is `SPDX-License-Identifier: GPL-2.0+`. The driver
produced here is a derivative work of both, hence this repo is
**GPL-2.0-or-later**. New source files must carry an SPDX
`GPL-2.0-or-later` tag and the depthcharge copyright header style.

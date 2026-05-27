<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# depthcharge IPQ4019 ethernet driver (Google Wifi / "gale")

A new **network driver for the Qualcomm IPQ4019 ESS EDMA** ethernet controller,
to be added to [depthcharge](https://chromium.googlesource.com/chromiumos/platform/depthcharge)
(the ChromeOS verified-boot payload) so that the **Google Wifi** router — board
codename **`gale`** — can do **TFTP netboot** from its *onboard* ethernet ports.

## Why

`gale` is a headless IPQ4019 device. depthcharge already supports netboot
(DHCP + TFTP + boot) via its `netboot` / `dev` payload images, but it has **no
driver for the IPQ4019's onboard ethernet**. The only Qualcomm NIC driver in the
gale-era tree (`src/drivers/net/ipq806x.c`) targets the *Synopsys DesignWare GMAC*
of the IPQ806x "storm"/OnHub sibling — a completely different MAC. So today the
only way to netboot `gale` is a USB-Ethernet dongle (`DRIVER_NET_ASIX`).

This project adds `src/drivers/net/ipq4019.c` (+ supporting MDIO/PHY/switch code)
implementing depthcharge's `NetDevice` interface for the **ESS EDMA at
`0xc080000`** with the **QCA8075 PSGMII** PHY + internal switch.

## Status

| Phase | Goal | State |
|-------|------|-------|
| 0 | Build environment + flash/recover loop (from scratch) | planned |
| 1 | Proof-of-life: one port links, raw TX/RX, DHCP reply seen | planned |
| 2 | TFTP netboot: download + boot a kernel (Ctrl+N / `netboot` image) | planned |
| 3 | Full driver: both ports, robust link, upstream-quality | planned |

## Repository layout

```
LICENSE              GPL-2.0 text (whole repo is GPL-2.0-or-later)
docs/
  design.md          Architecture & design (the "how", validated)
  hardware.md        IPQ4019 EDMA/PSGMII/switch register reference + base addresses
  references.md      Upstream source provenance, commit hashes, licensing notes
plan/
  README.md          Iterative execution model + phase index
  phase-0-*.md ...    Detailed, verifiable task breakdown per phase
reference/           Vendored upstream source (GPL-2.0+) used as port references
```

## How to use this repo

1. Read `docs/design.md` for the architecture and the U-Boot→depthcharge mapping.
2. Read `docs/hardware.md` for concrete register addresses and the bring-up recipe.
3. Work `plan/phase-0` → `phase-3` in order; each phase is an iterative
   build→flash→observe→fix loop with explicit exit criteria.

## License

Everything here is **GPL-2.0-or-later**. The driver is a derivative work of
depthcharge (`ipq806x.c`, GPL-2.0-or-later) and U-Boot (`essedma.c`,
GPL-2.0-or-later); see `docs/references.md`.

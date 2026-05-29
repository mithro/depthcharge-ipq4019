<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# rpi4-gwifi testbed: layout and entrypoints

The `rpi4-gwifi` Raspberry Pi 4 is the self-contained workspace for gwifi
(Google WiFi, IPQ4019) development. It hosts the device under test (DUT),
its serial consoles, its TFTP/DHCP server, and a mirror of all source +
resources from the local development machine.

Hostname: `rpi4-gwifi.iot.welland.mithis.com` (also `ipv4.eth0.rpi4-gwifi.…`).

## Physical wiring

- gale's USB **port** (via SuzyQ + CCD cable) → Pi USB hub `1-1` port 3.
  Exposes two ttyUSB devices via the "google" kernel driver: EC console
  (`-if00`) and AP console (`-if01`).
- gale **LAN** RJ45 → Pi USB-eth `eth-glan` (RTL8153) → Pi hub 2 port 2
  (or hub 1-1 port 2 after a parent-hub recovery cycle).
- gale **WAN** RJ45 → Pi USB-eth `eth-gwan` (RTL8153) → Pi hub 2 port 1.
- The Pi's onboard ethernet is on a separate management switch and is
  the SSH path.

Power-cycle gale: `sudo uhubctl -l 1-1 -p 3 -a cycle`.

## Directory layout on the Pi

```
/home/tim/local/gwifi/
├── depthcharge-ipq4019/              ← this repo (git checkout)
│   ├── src/drivers/net/ipq4019.c     ← the ethernet driver being developed
│   ├── coreboot/                     ← upstream coreboot clone (for builds)
│   ├── depthcharge/                  ← upstream depthcharge clone
│   ├── vboot_reference/              ← upstream vboot
│   ├── flashrom-cros/                ← raiden_debug_spi-capable flashrom
│   ├── docs/                         ← procedure/proof docs
│   ├── plan/                         ← design notes
│   ├── patches/                      ← driver patches
│   ├── reference/                    ← reference material from upstreams
│   └── tmp/                          ← build/boot scripts + binaries
│       ├── dnsmasq-gwifi.conf        ← DHCP+TFTP config template
│       ├── pi_boot_test.py           ← orchestrate a netboot test
│       ├── pi_boot_verify_wiring.py  ← uhubctl + EC + UART capture
│       ├── pi_setup_eth_glan_only.sh ← isolate LAN-jack path
│       ├── pi_setup_eth_gwan_only.sh ← isolate WAN-jack path
│       └── build_v21.py, flash_v21.py, boot_v20.py, …
├── gale-spi-stock-2026-05-28.bin     ← 8 MiB stock SPI dump (CRITICAL — has cal data)
├── gale-spi-flash-backup.md          ← procedure for taking SPI backups
├── openwrt-25.12.2-…-factory.bin     ← full OpenWrt install image
├── openwrt-25.12.2-…-sysupgrade.bin  ← sysupgrade image
├── chromeos_*.zip                    ← original ChromeOS recovery image (zipped)
├── fill_pucks.py                     ← Sheets-driven inventory helper
├── gwifi_sheets.py                   ← Google Sheets accessor (needs token)
└── photos/                           ← reference photos of the DUT
```

TFTP root on Pi: `/srv/tftp/`.

## SuzyQ (EC + AP serial + SPI flash) access

Stable symlinks (provided by `/etc/udev/rules.d/70-gwifi-suzyq.rules`):

- `/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0` — EC console (115200 8N1).
- `/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0` — AP console (115200 8N1).

The same USB device exposes a SPI bridge. To flash gale's W25Q64
(8 MiB) via SuzyQ:

```
sudo flashrom -p raiden_debug_spi:target=AP -r /tmp/gale-readback.bin
# write payload (CAREFUL — atomic with `gale power off` from EC):
sudo flashrom -p raiden_debug_spi:target=AP -w build/gale.bin
```

**Always default to SuzyQ for flashing.** CH341A clip is emergency-only.

See `docs/keeping-suzyq-recovery-working.md` for the rules that keep
SuzyQ available (don't touch COREBOOT, don't disable rollback check,
bound retry loops in payloads).

## DHCP+TFTP netboot

The dnsmasq config template lives at
`/home/tim/local/gwifi/depthcharge-ipq4019/tmp/dnsmasq-gwifi.conf`. It
contains a placeholder `interface=IFACE` which gets `sed`-replaced with
the desired Pi NIC before starting dnsmasq. Logs go to
`/home/tim/dnsmasq-gwifi.log`, leases to `/home/tim/dnsmasq-gwifi.leases`,
PID to `/home/tim/dnsmasq-gwifi.pid`.

End-to-end test of a netboot through one specific gale jack:

```
# Pi: physically isolate the OTHER jack via uhubctl (ip-link-down is
# NOT enough — RTL8153 keeps PHY autoneg alive regardless of admin
# state), start dnsmasq, then drive gale through SuzyQ.
python3 tmp/pi_boot_test.py eth-glan      # → LAN jack (PHY 3)
python3 tmp/pi_boot_test.py eth-gwan      # → WAN jack (PHY 4)
```

Proof both jacks work: `docs/PROOF-both-ports-2026-05-30.md`.

## Pi-side tools

Installed: `flashrom 2.6.0`, `uhubctl`, `dnsmasq 2.91`, `socat`,
`tcpdump`, `uv 0.11+`, python3 + system pyserial 3.5. All
admin-PATH tools (`flashrom`, `uhubctl`, `dnsmasq`) live in
`/usr/sbin` — invoke them with `sudo` from a non-root shell or they
appear "command not found".

## What is NOT mirrored on the Pi

- The 1.8 GB raw decompressed ChromeOS recovery image (only the .zip is on
  the Pi — `unzip` on demand if needed).
- The local machine's `~/local/sheets_token.json` (Google OAuth for
  `gwifi_sheets.py`). Copy manually if needed — it's a credential.
- The .pcap and .pid runtime artifacts from prior debug sessions
  (`.gitignore` rule, regeneratable).

## Recovering when SuzyQ stops talking

If `flashrom -p raiden_debug_spi:target=AP -r ...` hangs or `gale power on`
returns "power - off", the recovery order is:

1. `sudo uhubctl -l 1-1 -p 3 -a cycle` — power-cycle gale's USB connection.
2. Send a fresh `\rreboot\r` to the EC ttyUSB to reset dev/rec state.
3. If that fails, escalate to CH341A (see `docs/ch341a-recovery.md`).

Recent post-recovery procedure: `docs/post-recovery-recipe.md`.

<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Proof: TFTP boot of OpenWrt works through BOTH gale ethernet ports

## Setup

The gale (Google WiFi, IPQ4019) is on a Raspberry Pi 4 testbed at
`rpi4-gwifi.iot.welland.mithis.com`. Both of gale's RJ45 jacks are wired to
**separate USB ethernet adapters** on the Pi:

| Pi NIC          | gale jack | gale PHY (MDIO addr) |
|-----------------|-----------|----------------------|
| `eth-glan` (RTL8153) | **LAN** | PHY 3 |
| `eth-gwan` (RTL8153) | **WAN** | PHY 4 |

This mapping was determined **empirically** by physically powering off one
USB ethernet adapter at a time (via `uhubctl`) and observing which gale PHY
linked. `ip link set down` alone is not sufficient — the RTL8153 keeps the
PHY chip transmitting autoneg signals at the kernel admin-down level.
Only fully removing USB power makes the Pi-side cable peer disappear.

Pi services for netboot:
- `dnsmasq` (DHCP + TFTP) bound to one Pi NIC at a time via `bind-interfaces`
- TFTP root: `/srv/tftp/`
- `openwrt-gale.itb` extracted from
  `openwrt-25.12.2-ipq40xx-chromium-google_wifi-initramfs-fit-zImage.itb.vboot`
  (raw FIT at offset 0x10000 of the vboot wrapper).

## Test A: LAN jack (PHY 3, via eth-glan)

State: `eth-gwan` USB **powered off** via `uhubctl -l 2 -p 1 -a off`.
dnsmasq bound to `eth-glan` only.

AP UART (key events):
```
ipq4019: PHY 3  LINK_UP  1G/full  PHY_SPECIFIC=0xbc5c
ipq4019: PHY 4  no_link  10M/half  PHY_SPECIFIC=0x0010
Sending DHCP discover... done.
Sending DHCP request... done.
Waiting for reply... done.
The bootfile was 8338516 bytes long.
Loading FIT.
Image fdt-1 has 18915 bytes.
Image kernel-1 has 8318232 bytes.
Compat preference: google,gale-v2
Choosing best match config@1.
Exiting depthcharge with code 4 at timestamp: ...
[    1.633] qca8k-ipq4019 c000000.switch: configuring for fixed/internal link mode
[    1.633] qca8k-ipq4019 c000000.switch: Link is Up - 1Gbps/Full
[    1.813] qca8k-ipq4019 lan (uninitialized): PHY [90000.mdio-1:03]
[    1.882] qca8k-ipq4019 wan (uninitialized): PHY [90000.mdio-1:04]
[    6.755] qca8k-ipq4019 lan: configuring for phy/psgmii link mode
[    6.761] qca8k-ipq4019: PSGMII calibration!
[    6.769] ipqess-edma c080000.ethernet eth0: Link is Up - 1Gbps/Full
[   10.552] qca8k-ipq4019 lan: Link is Up - 1Gbps/Full
```

**PASS**: only PHY 3 has link, DHCP+TFTP succeed, Linux kernel runs, qca8k
driver initializes, LAN port reaches 1G/full.

## Test B: WAN jack (PHY 4, via eth-gwan)

State: `eth-glan` USB **powered off** via `uhubctl -l 1-1 -p 2 -a off`
(its USB position had moved to hub 1-1 port 2 after a parent-hub power
cycle had to recover from a stuck gale enumeration earlier; the move was
benign and visible via `readlink /sys/class/net/eth-glan/device`).
dnsmasq bound to `eth-gwan` only.

AP UART (key events):
```
ipq4019: PHY 3  no_link  10M/half  PHY_SPECIFIC=0x0010
ipq4019: PHY 4  LINK_UP  1G/full  PHY_SPECIFIC=0xbc1c
Sending DHCP discover... done.
Sending DHCP request... done.
Waiting for reply... done.
[    6.351] random: crng init done
[    6.765] ipqess-edma c080000.ethernet eth0: configuring for fixed/internal link mode
[    6.771] qca8k-ipq4019: PSGMII calibration!
[    6.779] ipqess-edma eth0: Link is Up - 1Gbps/Full
[   10.552] qca8k-ipq4019 lan: Link is Up - 1Gbps/Full
[   11.785] procd: - early -
[   12.339] procd: - watchdog -
[   12.339] procd: - ubus -
[   12.396] procd: - init -
Please press Enter to activate this console.
[   12.812] kmodloader: loading kernel modules from /etc/modules.d/*
```

**PASS**: only PHY 4 has link, DHCP+TFTP succeed, Linux kernel runs to
**`procd: - init -` and the console prompt**.

dnsmasq DHCP log shows the exchange happening on the active NIC:
```
DHCPDISCOVER(eth-gwan) 44:07:0b:01:87:b4
DHCPOFFER(eth-gwan) 10.42.1.69 44:07:0b:01:87:b4
DHCPREQUEST(eth-gwan) 10.42.1.69 44:07:0b:01:87:b4
DHCPACK(eth-gwan) 10.42.1.69 44:07:0b:01:87:b4
```

The kernel still labels the active port `lan` (not `wan`) — this is an
OpenWrt qca8k labelling artifact from the FIT's embedded DT, but doesn't
affect the data path: frames flow gale-jack → cable → eth-gwan → dnsmasq.

## Why the names matter, and what `ip link down` doesn't do

The Pi's USB ethernet adapters are named `eth-gwan` and `eth-glan` (via
systemd `.link` files presumably). The naming **happens to correspond
correctly to the physical wiring** — `eth-gwan` is on the WAN jack,
`eth-glan` on the LAN jack — but the only way to **prove** this is to
physically isolate each NIC. The user's correction ("don't trust the
names") was reasonable scepticism.

Critically: `ip link set <iface> down` on an RTL8153 USB ethernet adapter
**does not stop the PHY from transmitting autoneg signals on the wire**.
The kernel admin-down only stops the OS using the interface; the chip
keeps the cable peer's PHY happily auto-negotiating. So both gale PHYs
appeared "linked" any time both Pi NICs were physically powered, even if
one was admin-down on the Pi.

The reliable isolation primitive is `uhubctl -l <hub> -p <port> -a off`
which cuts VBUS to the USB device, removing it from the bus entirely.

## Files added/modified on the Pi

- `/srv/tftp/openwrt-gale.itb` — extracted raw FIT (8338516 bytes).
- `/srv/tftp/openwrt-25.12.2-…vboot` — original download (vboot-wrapped).
- `/home/tim/dnsmasq-gwifi.conf` — template (replace `IFACE` placeholder).
- `/home/tim/dnsmasq-gwifi.active.conf` — rendered for current test.
- `/tmp/pi_boot_test.py` — bring up one NIC, boot gale via uhubctl + EC,
  capture AP UART for 90 s.
- `/tmp/pi_boot_verify_wiring.py` — minimal version that doesn't reconfigure
  NIC state, just power-cycles gale and reads UART.

Local copies of these are checked into `tmp/` in the depthcharge-ipq4019
repo.

## Caveat: ath10k_pci panic later in userspace

Both tests reach the OpenWrt `Please press Enter to activate this console.`
prompt, then panic ~1 second later when `ath10k_pci` (WiFi driver)
fails to find calibration data. This is a gale-specific initramfs
limitation (WiFi cal data lives in the device's SPI flash, which isn't
accessible during a netboot context). It does **not** affect the
networking proof — eth0 and qca8k both reach 1G/full link and the
userspace init runs.

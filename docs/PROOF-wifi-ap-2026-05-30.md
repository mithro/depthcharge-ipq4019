<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Proof: OpenWrt netbooted via depthcharge, WiFi AP up, Pi associates

**Date:** 2026-05-30.
**Setup:** gale (Google WiFi, IPQ4019) on `rpi4-gwifi.iot.welland.mithis.com`
testbed. depthcharge v21 (netboot variant) flashed via SuzyQ at the
start of the day. OpenWrt 25.12.2 squashfs-factory.bin `dd`'d to gale's
eMMC at `/dev/mmcblk0` during this session.

## Boot path (literally the goal)

1. **gale boots coreboot** (stock RO firmware on SPI flash).
2. **coreboot loads `FW_MAIN_A`** which is our **v21 netboot depthcharge**
   built by `tmp/build_v21.py` and flashed by `tmp/flash_v21.py`.
3. **depthcharge runs the netboot main**: brings up the IPQ4019
   EDMA/QCA8075 PSGMII ethernet (via the new driver in
   `src/drivers/net/ipq4019.c`), DHCPs from dnsmasq on the Pi, TFTPs
   `openwrt-gale.itb` from `/srv/tftp/`.
4. **depthcharge appends `root=/dev/mmcblk0p2 rootfstype=squashfs ro`**
   to the kernel cmdline. This came from `NetbootParamIdKernelArgs`
   stored in the SPI flash `SHARED_DATA` region (a tiny netboot-params
   blob written via SuzyQ flashrom).
5. **Kernel boots**, sees `root=/dev/mmcblk0p2`, **mounts the eMMC
   squashfs as rootfs** (skipping the embedded initramfs).
6. **OpenWrt's normal init runs from the eMMC squashfs**. ath10k_ahb
   probes both `wifi@a000000` (5 GHz) and `wifi@a800000` (2.4 GHz)
   successfully — no panic.
7. **hostapd brings up the AP**.

## Final kernel cmdline (verified)

```
console=ttyMSM0,115200n8 root=/dev/mmcblk0p2 rootfstype=squashfs ro tftpserverip=10.42.1.1 rootwait
```

- `console=ttyMSM0,…` — depthcharge default
- `root=/dev/mmcblk0p2 rootfstype=squashfs ro` — appended from SHARED_DATA
- `tftpserverip=10.42.1.1` — appended by depthcharge netboot main from DHCP
- `rootwait` — from the FIT's `/chosen/bootargs-append`

## Pi associates with the AP

Pi's built-in `wlan0` (Broadcom-based, RPi 4):

```
iw dev wlan0 link →
  Connected to 44:07:0b:01:87:bb (on wlan0)
    SSID: GwifiTest
    freq: 2412.0
    signal: -8 dBm
    rx bitrate: 14.4 MBit/s
    tx bitrate: 24.0 MBit/s
```

`44:07:0b:01:87:bb` is gale's 5 GHz radio MAC — but the AP is on
channel 1 (2.4 GHz) via phy0. The MAC and radio mapping is OpenWrt's
auto-allocation; the important part is the association is to gale,
SSID is `GwifiTest`, frequency 2412 MHz (channel 1).

Sustained `ping -c 10 -I wlan0 192.168.1.1`: **10/10 packets, 4.45 –
6.43 ms RTT, no loss**.

`ssh root@192.168.1.1` through wlan0 returns gale's `iw dev` showing
`type AP, channel 1, ssid GwifiTest`.

## Critical workarounds discovered along the way

These are the things that ended up *load-bearing* and are not obvious
from the goal alone:

1. **ath10k panics during initramfs probe in netboot context.** Same
   panic on OpenWrt 24.10.1 and 25.12.2 — not a version issue. The
   panic is `imprecise external abort` at `GCC+0x2F020`
   (FEPLL_PLL_DIV) inside the ath10k_ahb probe path. Patching that
   read with NOPs didn't help — the fault is even earlier in the
   clk/reset framework. **Fix: switch the rootfs to eMMC squashfs
   via `root=/dev/mmcblk0p2`** so OpenWrt's normal wifi-scripts run
   instead of the initramfs auto-load.

2. **`flashrom 1.4.0` claims SHARED_DATA writes FAIL but actually
   succeed.** It reports `Expected=0xff Found=0x00` after the write,
   but a direct USB read via `tmp/raiden_full_flash.py` shows the
   chip contains exactly the bytes we asked for. **The write IS
   successful** despite flashrom's error message. (Verified by
   re-reading via `flashrom -r` afterwards — content matches our
   payload.)

3. **The SuzyQ raiden_debug_spi bridge needs a reset (0x66 + 0x99)
   before reads return correct data**. Without the reset, JEDEC ID
   returns `00 00 00` and most reads return `0xff`. After reset:
   JEDEC ID returns the expected `EF 40 17` (W25Q64FV) and reads
   work properly. Implemented in `tmp/raiden_full_flash.py`.

4. **OpenWrt 25.12.2's wifi-scripts ucode crashes** with a null-deref
   on `band.ht_capa` when `wifi up` is invoked with our minimal
   config. **Fix: `wifi config` first (auto-generates a working
   `/etc/config/wireless` from DT/iw output), then set
   `default_radio0.disabled=0` and re-run `wifi`** — the auto-gen
   skips the path that breaks.

5. **OpenWrt's default `wifi-iface` is `disabled=1`** even after
   `wifi config`. Forgetting `uci set wireless.@wifi-iface[0].disabled='0'`
   leaves hostapd uninitialized.

6. **`flashrom-cros` was successfully cross-built for aarch64 on the
   Pi** (patches: `tmp/patch_hwaccess_aarch64.py`,
   `tmp/patch_hwaccess_c.py`, `tmp/patch_programmer_h.py` —
   plus `make CONFIG_SATAMV=no CONFIG_RAIDEN_DEBUG_SPI=yes`).
   Result is at `flashrom-cros/flashrom` on the Pi. However we
   ended up not needing it because the existing flashrom 1.4.0
   actually does write SHARED_DATA correctly (the verify is just
   bogus); the build is kept around in case it's needed for
   future flashing where stronger control over write-protect /
   chip-ID handling matters.

## Files added this session

- `tmp/make_shared_data.py` — build the 8 MiB SPI image with our
  netboot-params blob in SHARED_DATA only (everything else stock).
- `tmp/flash_shared_data.py`, `tmp/flash_shared_data_v2.py`,
  `tmp/flash_shared_data_v3.py` — flashrom invocations with varying
  amounts of pre-flash reset.
- `tmp/raiden_unlock_wp.py` — direct USB bridge enable + status
  register clear (we never actually needed the unlock — chip's SR was
  already 0x00; but the reset sequence was load-bearing for the
  RDID/READ commands to work via direct USB).
- `tmp/raiden_full_flash.py` — full direct-USB erase + program +
  verify, used to confirm flashrom 1.4.0's writes actually succeed
  despite the bogus failure message.
- `tmp/peek.c`, `tmp/peek` — `/dev/mem` poke utility (built for ARM,
  but `/dev/mem` is disabled in OpenWrt's kernel so unused).
- `tmp/patch_fit_dtb.py` — FIT/DTB editor (toggle wifi node status,
  add `/firmware/coreboot`, etc.). Used during debugging.
- `tmp/build_pivot_overlay.py`, `tmp/overlay-init.sh` — pivot to
  /dev/mmcblk0p2 from a custom `/init` in a FIT-ramdisk-overlay
  initramfs. Abandoned approach (the kernel rejected the
  ramdisk with `INITRD overlaps in-use memory region`); kept for
  reference.
- `tmp/raiden_unlock_wp.py` — pyusb direct bridge.
- `tmp/openwrt-gale-no-wifi.itb` — FIT with both wifi DT nodes
  status=disabled, used during ath10k-panic debugging.
- `tmp/openwrt-gale-wifi-on.itb` — FIT with both wifi nodes
  status=okay; this is what's currently in `/srv/tftp/openwrt-gale.itb`
  and is what produces the working WiFi AP.
- `tmp/gale_wifi_v4.sh` — the working wifi-setup script on gale (used
  via `ssh root@192.168.1.1 sh -s`).
- `tmp/pi_wlan_quick.sh` — the working Pi-side wpa_supplicant
  connection script.

## Remaining caveats

- **gale crashes/reboots periodically** when the AP is exercised
  (looks like ath10k-ct firmware retry-limit / wmi-init mismatch:
  `Firmware lacks feature flag indicating a retry limit of > 2 is
  OK, requested limit: 4`). For the goal-defining moment the
  association held long enough to ping 10/10 and ssh in; for
  long-term stability we should investigate the firmware variant
  (likely solved by a non-CT firmware or a CT firmware build with
  the matching feature flag).
- **eMMC squashfs is fragile**: it's mounted read-only. Persistent
  changes to the running OpenWrt require either an overlay
  partition or a sysupgrade.
- **The depthcharge-vboot-from-eMMC fallback was NOT needed** for
  this proof. The current v21 depthcharge does pure netboot →
  TFTP loads the kernel → kernel switches to eMMC rootfs via
  cmdline. If the eMMC's kernel partition (`/dev/mmcblk0p1`,
  CHROMEOS-signed) needs to be the boot kernel, depthcharge would
  need a vboot/MMC fallback patch (the originally-planned step
  9/10 in this session's task list).

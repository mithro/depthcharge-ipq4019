<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Post-recovery recipe — from CH341A restore to TFTP-booting OpenWrt

This is the **mechanical sequence** to run after physically restoring the gale
to stock with a CH341A SPI flash clip. The sequence is laid out so that — given
the current state of this repo at commit `eac9a9d` (or later), with the
pre-flight fixes from code review applied — there's no improvisation between
"stock booting again" and "OpenWrt initramfs prompt over TFTP".

## State assumed before starting

- gale SPI flash has been written back to stock via CH341A clip with
  `/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin` (sha256
  `735b1c5adc3399d8257915d28b3df0313c3e2f64ab8385297c5b1a7eb10012d9`).
- gale powered on, SuzyQ cable attached.
- This repo is at HEAD (`git -C /home/tim/local/gwifi/depthcharge-ipq4019 log --oneline -1`).
- Build environment is intact (`docs/build.md` step 4 has been run at least
  once). The current binary is `depthcharge/build/netboot.payload`. If you
  modified anything in `src/drivers/net/`, re-copy and rebuild:

  ```
  cp src/drivers/net/ipq4019* depthcharge/src/drivers/net/
  cd depthcharge
  make BOARD=gale netboot_unified \
      LIBPAYLOAD_DIR=$PWD/../coreboot/payloads/libpayload/install/libpayload \
      VB_SOURCE=$PWD/../vboot_reference \
      -j$(nproc)
  ```

## Step 1 — Verify stock is alive

```
# Cycle so we know the state is clean
uv run --no-project python tmp/rootport_cycle.py
# Watch the AP UART for ~15s — coreboot bootblock banner should appear,
# then depthcharge messages, then either VbBootDeveloper (dev mode) or
# VbBootRecovery (recovery)
uv run --no-project python tmp/bootcap.py
```

You should see lines beginning with "coreboot", "depthcharge", "VbBoot…".
If the AP is silent: SOMETHING is still wrong with the flashed image —
do **not** proceed.

## Step 2 — Sanity-check raiden_debug_spi access

The reason stock was needed is that **stock's depthcharge recovery loop
releases the SPI bus periodically**, so the EC bridge can reflash. Verify
this works:

```
uv run --no-project python -c "
import subprocess
r = subprocess.run(
    ['sudo','/usr/sbin/flashrom','-p','raiden_debug_spi',
     '-c','W25Q64BV/W25Q64CV/W25Q64FV','--flash-name'],
    capture_output=True, text=True, timeout=15)
print('rc:', r.returncode); print(r.stdout + r.stderr)
"
```

Expected: rc=0, "vendor=Winbond name=W25Q64BV/W25Q64CV/W25Q64FV".

If it says "No EEPROM/flash device found": something is wrong with the
restore. Re-verify stock dump bytes match the saved file via the CH341A
before doing anything else.

## Step 3 — Read back the current chip + compare to stock

```
uv run --no-project python tmp/con.py "gale power off"   # AP off, flash powered
sudo /usr/sbin/flashrom -p raiden_debug_spi \
    -c 'W25Q64BV/W25Q64CV/W25Q64FV' \
    -r tmp/post-restore-readback.bin
uv run --no-project python -c "
import hashlib
got = open('tmp/post-restore-readback.bin','rb').read()
exp = open('/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin','rb').read()
print('Size match:', len(got)==len(exp))
print('SHA256 match:', hashlib.sha256(got).hexdigest()==hashlib.sha256(exp).hexdigest())
"
```

Both should be True.

## Step 4 — Build the netboot image (stock + new payload in FW_MAIN_A/B)

```
uv run --no-project python tmp/build_image_rw.py
# Output:
#   tmp/gale-netboot-rw.bin = stock 8MiB image with
#     FW_MAIN_A's fallback/payload swapped for depthcharge/build/netboot.elf
#     FW_MAIN_B's fallback/payload swapped for depthcharge/build/netboot.elf
#   No re-signing because the RW preamble carries USE_RO_NORMAL, which means
#   "load RW body but skip its verification". The keyblock/preamble stay valid.
#   COREBOOT (RO) is left at stock — DO NOT TOUCH IT.
```

## Step 5 — Flash FW_MAIN_A

```
uv run --no-project python tmp/flash_rw.py FW_MAIN_A
# Expected: "VERIFIED" then "RESULT: SUCCESS"
# If verify fails, do NOT retry blindly — first re-read the chip to check
# whether the previous write actually corrupted FW_MAIN_A or whether the
# verify just hit a transient bus glitch.
```

(If FW_MAIN_A flash succeeds, also flash FW_MAIN_B for symmetry —
`uv run --no-project python tmp/flash_rw.py FW_MAIN_B`. Not strictly
required for normal boot, but it gives a fallback if RW_SECTION_A fails
to load.)

## Step 6 — Switch the device to dev mode + reboot

Dev mode causes vboot to load the **RW** firmware body (which is what we
just flashed) without showing the recovery screen.

```
uv run --no-project python -c "
import time, serial
EC = '/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0'
s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
s.dtr = False; s.rts = False; s.open()
for c in ('gale dev on','gale rec off','reboot'):
    s.write((c + '\r').encode()); s.flush(); time.sleep(0.4)
s.close()
"
```

## Step 7 — Start the DHCP+TFTP server

```
uv run --no-project python tmp/netboot_server.py &
# Serves DHCP on enx00e04c68016b (10.42.1.1) with bootfile openwrt-gale.itb.
# Confirm the OpenWrt FIT is at tmp/tftproot/openwrt-gale.itb:
ls -la tmp/tftproot/openwrt-gale.itb
# Expected size: 8338516 bytes (raw FDT, magic d00dfeed at offset 0).
```

## Step 8 — Capture the boot

```
uv run --no-project python tmp/bootcap.py 60   # 60-second capture window
```

What you SHOULD see (in order):
1. coreboot bootblock banner.
2. depthcharge banner.
3. **`ipq4019: MAC xx:xx:xx:xx:xx:xx`** — driver `eth_init` started.
4. **`ipq4019: mdio_init`**.
5. **PHY-ID probe loop output** for addresses 0..5.
6. **`ipq4019: psgmii self-test passed (try N)`** — *this is the gate
   that the two new bug fixes (P1-K GCC_ESS_BCR + P2-F retry) unblock*.
7. **`ipq4019: switch init`**, **`ipq4019: edma init`**.
8. **`ipq4019: init done, net_add_device`**.
9. depthcharge: `Waiting for network link...`.
10. **Link comes up** on whichever port the netboot host is attached to.
11. **`DHCPDISCOVER`** seen on the host's dnsmasq log; gale assigned 10.42.1.x.
    *(This is the gate that the P1-N EOP TPD length fix unblocks — if TX
    sent malformed frames, no DHCP request would reach the server.)*
12. **TFTP GET openwrt-gale.itb** from gale.
13. **`Starting kernel...`** with load address 0x80208000.
14. Linux boot messages → OpenWrt initramfs login prompt.

## What to do at each new boot-stage stall

- **No `mdio_init`**: `ipq4019_eth_driver_register` not registered or
  `usb_eth` is crashing first → check the `usb_eth` guard in
  `patches/0001-add-ipq4019-net-driver.patch`.
- **PHY probe loop fails (all addresses return 0xffff)**: MDIO accessor
  is wrong, or coreboot didn't clock-out MDIO → review `ipq4019_mdio.c`
  and check `IPQ4019_MDIO_BASE` matches `hardware.md`.
- **"PSGMII PLL_VCO_CALIB Not Ready" / "did not converge"**: GCC_ESS_BCR
  offset or the PSGMII calibration timing is wrong. The offset is now
  0x12008 (verified against Linux gcc-ipq4019.c, commit `6d5a3b0`); if
  still failing, the calibration delay loop or register layout differs
  from U-Boot's reference.
- **switch init OK but no link**: PHY hasn't completed auto-negotiation,
  or `ess_switch_enable_lookup` is gating CPU↔LAN forwarding. Compare
  port-vid programming against U-Boot `ess_port_vlan_enable`.
- **Link up but no DHCP**: TX frames may still be malformed. Inspect on
  the host with `sudo tcpdump -i enx00e04c68016b -nn -e -vv`. If you
  see frames with weird short lengths, P1-N fix may not have taken
  effect.
- **DHCP OK but TFTP fails**: increase TFTP block size or check the
  dnsmasq log for read errors; the raw `.itb` is 8.3 MB and must be
  served in full.
- **Kernel loaded but doesn't boot**: load address or FDT problem; the
  raw FIT's `Load Address: 0x80208000` must match
  `CONFIG_KERNEL_START` (which it does per the verification in
  `docs/bringup-log.md`).

## Quick reference — files involved

| File | Role |
|---|---|
| `/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin` | Stock dump for CH341A restore. |
| `src/drivers/net/ipq4019.c`, `.h`, `_mdio.c`, `_psgmii.c` | Driver source (authoritative). |
| `patches/0001-add-ipq4019-net-driver.patch` | depthcharge tree patch (driver + Kconfig + usb_eth guard). |
| `tmp/build_image_rw.py` | Splice new payload into stock image → `tmp/gale-netboot-rw.bin`. |
| `tmp/flash_rw.py` | AP-off + flashrom -w of FW_MAIN_A (or FW_MAIN_B). |
| `tmp/netboot_server.py` | dnsmasq DHCP+TFTP on `enx00e04c68016b` (10.42.1.1). |
| `tmp/tftproot/openwrt-gale.itb` | Raw FIT (8338516 B) — kernel-1 + google_wifi DTB, load 0x80208000. |
| `tmp/bootcap.py` | Capture AP UART for N seconds. |
| `tmp/con.py` | Send one EC console command. |
| `tmp/rootport_cycle.py` | Power-cycle the gale via `usb3-port1/disable`. |

## What NOT to do

- **Never** flash COREBOOT (RO) on this device again, even with a verified
  binary. The whole point of Approach A is that stock's recovery loop in
  RO is the ONLY non-destructive reflash path; replacing it removes the
  safety net.
- **Never** start an erase if a clean read isn't verified first (this
  session's lesson — see `docs/bringup-log.md` §"Update: SPI bus deadlock").
- **Never** run multi-cycle catch loops on a contended bus — each
  contended write degrades the chip further (this session: detection
  rate went 25 % → 0 % over a few hundred attempts).

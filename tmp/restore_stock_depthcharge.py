#!/usr/bin/env python3
"""Restore stock VBLOCK_A, VBLOCK_B, FW_MAIN_A, FW_MAIN_B, RW_FWID_A,
RW_FWID_B from gale-spi-stock-2026-05-28.bin via SuzyQ flashrom.

This brings back the stock vboot depthcharge which boots OpenWrt from
eMMC. Keeps COREBOOT (RO firmware) byte-identical — we never touch RO.
"""
import subprocess, time, sys, serial

STOCK = "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"

def ec_send(cmd, wait=1.0, read=True):
    try:
        s = serial.Serial(EC, 115200, timeout=0.2)
        s.write(b"\r"); time.sleep(0.2)
        try: s.read(8192)
        except Exception: pass
        s.write((cmd + "\r").encode()); time.sleep(wait)
        if read:
            try:
                print(s.read(4096).decode("latin1", "replace").rstrip(), flush=True)
            except Exception as e:
                print(f"  (read err: {e})", flush=True)
        s.close()
    except Exception as e:
        print(f"  EC open err (ignored): {e}", flush=True)


print("=== gale power off ===")
ec_send("gale power off", 2)
time.sleep(2)

print("=== flashrom -w stock --image VBLOCK_A,B + FW_MAIN_A,B + RW_FWID_A,B ===")
r = subprocess.run(
    ["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
     "--fmap", "-w", STOCK,
     "-i", "VBLOCK_A", "-i", "VBLOCK_B",
     "-i", "FW_MAIN_A", "-i", "FW_MAIN_B",
     "-i", "RW_FWID_A", "-i", "RW_FWID_B"],
    capture_output=True, text=True, timeout=300)
for ln in (r.stdout + r.stderr).splitlines()[-30:]:
    print(f"  | {ln}")
print(f"exit: {r.returncode}")

if r.returncode == 0:
    print()
    print("=== gale dev off, rec off, power on ===")
    ec_send("gale dev off", 1)
    ec_send("gale rec off", 1)
    ec_send("gale power on", 1.5)
    print()
    print("OK — gale should now boot from eMMC (no TFTP needed)")
else:
    sys.exit(r.returncode)

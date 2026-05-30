#!/usr/bin/env python3
"""Flash ONLY the SHARED_DATA fmap region via SuzyQ.

Idempotent: reads the current state of the chip, applies the local
SHARED_DATA region of the new image, and lets flashrom skip equal
sectors. RW region only — RO/COREBOOT/VBLOCK/FW_MAIN are untouched
(flashrom --image SHARED_DATA enforces this).

Atomic with `gale power off` from the EC so the AP cannot fight us
for the SPI bus during the write.
"""
import subprocess, time, sys, os, serial

ROOT = "/home/tim/local/gwifi/depthcharge-ipq4019"
NEW  = f"{ROOT}/tmp/gale-shared-data-v22.bin"
EC   = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"


def sh(cmd, check=True, **kw):
    print(f"  $ {cmd}", flush=True)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)
    if r.stdout.strip():
        for ln in r.stdout.strip().splitlines()[-12:]:
            print(f"    {ln}", flush=True)
    if r.stderr.strip():
        for ln in r.stderr.strip().splitlines()[-12:]:
            print(f"    err: {ln}", flush=True)
    if check and r.returncode != 0:
        sys.exit(f"FAILED ({r.returncode}): {cmd}")
    return r

def ec_open():
    return serial.Serial(EC, 115200, timeout=0.2)

def ec_cmd(ec, cmd, wait=0.5):
    ec.write(b"\r"); time.sleep(0.15); ec.read(8192)
    ec.write((cmd + "\r").encode()); time.sleep(wait)
    return ec.read(16384).decode("latin1", "replace").rstrip()


assert os.path.exists(NEW), f"missing {NEW}"
print(f"new image: {NEW}  size={os.path.getsize(NEW)}")

print("=== power off the AP via EC (atomic flash) ===")
ec = ec_open()
print(ec_cmd(ec, "gale power off", 1.0))
ec.close()
time.sleep(2)

print("=== flashrom write SHARED_DATA region only ===")
sh(f"sudo flashrom -p raiden_debug_spi:target=AP --fmap "
   f"-w {NEW} --image SHARED_DATA")

print("=== flashrom verify SHARED_DATA region only ===")
sh(f"sudo flashrom -p raiden_debug_spi:target=AP --fmap "
   f"-v {NEW} --image SHARED_DATA")

print("=== power the AP back on ===")
ec = ec_open()
print(ec_cmd(ec, "gale dev off"))
print(ec_cmd(ec, "gale rec off"))
print(ec_cmd(ec, "gale power on", 1.5))
ec.close()

print("OK")

#!/usr/bin/env python3
"""Decisive test: EC-reboot to power the AP, then raiden-read the SPI and
compare to the stock dump to judge whether raiden access is clean."""
import time, subprocess, serial, os

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/home/tim/local/gwifi/depthcharge-ipq4019/flashrom-cros/flashrom"
STOCK = "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"
OUT = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/raiden_read.bin"

def ec_reboot():
    try:
        s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
        s.dtr = False; s.rts = False; s.open()
        s.write(b"reboot\r"); s.flush(); time.sleep(0.5); s.close()
    except Exception as e:
        print("ec reboot note:", e)

print("[EC reboot -> AP powers to recovery loop]")
ec_reboot()
print("[wait 14s for re-enumeration + AP boot]")
time.sleep(14)

print("[raiden full read -> raiden_read.bin]")
r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-r", OUT],
                   capture_output=True, text=True, timeout=400)
print("flashrom stdout/stderr tail:")
for ln in (r.stdout + r.stderr).splitlines()[-8:]:
    print("  |", ln)
print("flashrom exit:", r.returncode)

if os.path.exists(OUT):
    a = open(OUT, "rb").read()
    b = open(STOCK, "rb").read()
    print(f"read size={len(a)} stock size={len(b)}")
    n = min(len(a), len(b))
    same = sum(1 for i in range(n) if a[i] == b[i])
    print(f"byte match vs stock: {100*same/n:.2f}%  ({same}/{n})")
    # show first 16 bytes of each
    print("read [0:16]:", a[:16].hex())
    print("stock[0:16]:", b[:16].hex())
else:
    print("no output file produced")

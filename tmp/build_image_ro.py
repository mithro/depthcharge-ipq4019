#!/usr/bin/env python3
"""Approach B: swap the RO depthcharge payload (COREBOOT region fallback/payload)
for my netboot depthcharge. No signing (RO is HW-trusted). Only COREBOOT changes.
Produces tmp/gale-netboot-ro.bin; no HW write."""
import subprocess, shutil, sys, os

ROOT = "/home/tim/local/gwifi/depthcharge-ipq4019"
CB = f"{ROOT}/coreboot/util/cbfstool/cbfstool"
ELF = f"{ROOT}/depthcharge/build/netboot.elf"
STOCK = "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"
OUT = f"{ROOT}/tmp/gale-netboot-ro.bin"

def run(args):
    print("  $", " ".join(os.path.basename(str(a)) if "/" in str(a) else str(a) for a in args))
    r = subprocess.run(args, capture_output=True, text=True)
    o = (r.stdout + r.stderr).strip()
    for ln in o.splitlines()[-4:]:
        print("    ", ln)
    if r.returncode:
        print("  !! exit", r.returncode); sys.exit(1)

print("[1] copy stock -> gale-netboot-ro.bin")
shutil.copy(STOCK, OUT)
print("[2] replace RO fallback/payload with netboot depthcharge (COREBOOT region)")
run([CB, OUT, "remove", "-r", "COREBOOT", "-n", "fallback/payload"])
run([CB, OUT, "add-payload", "-r", "COREBOOT", "-n", "fallback/payload", "-f", ELF, "-c", "lzma"])
print("[3] verify the swap")
r = subprocess.run([CB, OUT, "print", "-r", "COREBOOT"], capture_output=True, text=True)
for ln in r.stdout.splitlines():
    if "payload" in ln or "Name" in ln:
        print("    ", ln)
# sanity: only COREBOOT region differs from stock
a = open(OUT, "rb").read(); b = open(STOCK, "rb").read()
diff = [i for i in range(0, len(a), 256) if a[i] != b[i]]
if diff:
    print(f"    changed bytes (256B-sampled) span 0x{diff[0]:x}..0x{diff[-1]:x} (COREBOOT is 0x0..0x300000)")
print("output:", OUT, os.path.getsize(OUT), "bytes")

#!/usr/bin/env python3
"""RW path (no resign): swap FW_MAIN_A/B fallback/payload for my netboot
depthcharge. FW_MAIN_A/B are OUTSIDE WP_RO -> writable AP-off, no WP deassert.
USE_RO_NORMAL means the RW body isn't verified, so no re-signing is needed.
Produces tmp/gale-netboot-rw.bin."""
import subprocess, shutil, sys, os

ROOT = "/home/tim/local/gwifi/depthcharge-ipq4019"
CB = f"{ROOT}/coreboot/util/cbfstool/cbfstool"
ELF = f"{ROOT}/depthcharge/build/netboot.elf"
STOCK = "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"
OUT = f"{ROOT}/tmp/gale-netboot-rw.bin"

def run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        print("  !!", (r.stdout + r.stderr).strip()[-200:]); sys.exit(1)

shutil.copy(STOCK, OUT)
for region in ("FW_MAIN_A", "FW_MAIN_B"):
    run([CB, OUT, "remove", "-r", region, "-n", "fallback/payload"])
    run([CB, OUT, "add-payload", "-r", region, "-n", "fallback/payload", "-f", ELF, "-c", "lzma"])
    r = subprocess.run([CB, OUT, "print", "-r", region], capture_output=True, text=True)
    for ln in r.stdout.splitlines():
        if "fallback/payload" in ln:
            print(f"  {region}: {ln.strip()}")
print("output:", OUT, os.path.getsize(OUT), "bytes (FW_MAIN_A/B payload swapped, no resign)")

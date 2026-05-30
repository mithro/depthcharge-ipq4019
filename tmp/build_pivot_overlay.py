#!/usr/bin/env python3
"""Build an initramfs overlay cpio whose /sbin/init is a pivot script
that switch_roots to the OpenWrt squashfs on /dev/mmcblk0p2.

The initramfs overlay is unpacked on top of the embedded OpenWrt
initramfs, so /sbin/init from this overlay REPLACES procd. The kernel
calls /sbin/init (now our script) which pivots to the MMC rootfs and
exec's the real /sbin/init from there.
"""
import os, shutil, subprocess

ROOT = "/home/tim/local/gwifi/depthcharge-ipq4019"
SCRIPT_SRC = f"{ROOT}/tmp/overlay-init.sh"
OUT = f"{ROOT}/tmp/openwrt-pivot-overlay.cpio"
STAGE = f"{ROOT}/tmp/pivot-overlay-stage"

if os.path.exists(STAGE):
    shutil.rmtree(STAGE)
os.makedirs(STAGE)
# Kernel tries /init first, before /sbin/init. So we put the pivot
# script at /init (overriding the built-in initramfs's /init which is
# a symlink to /sbin/procd).
shutil.copy(SCRIPT_SRC, f"{STAGE}/init")
os.chmod(f"{STAGE}/init", 0o755)

paths = ["init"]
proc = subprocess.run(
    ["cpio", "-o", "-H", "newc", "--reproducible", "--owner=0:0"],
    cwd=STAGE, input="\n".join(paths).encode(),
    capture_output=True,
)
print("cpio stderr:", proc.stderr.decode())
if proc.returncode != 0:
    raise SystemExit("cpio failed")

import lzma
# Use xz with --check=crc32 and embedded header. Kernel initramfs
# unpacker reliably handles xz format.
xzdata = lzma.compress(proc.stdout,
                       format=lzma.FORMAT_XZ,
                       check=lzma.CHECK_CRC32,
                       preset=6)
with open(OUT, "wb") as f:
    f.write(xzdata)
print(f"Wrote {OUT} ({len(xzdata)} bytes xz, {len(proc.stdout)} bytes raw)")
print(f"  xz magic: {xzdata[:6].hex()}")

ls = subprocess.run(["cpio", "-itv", "--quiet"], input=proc.stdout, capture_output=True)
print("=== Archive contents (uncompressed) ===")
print(ls.stdout.decode())

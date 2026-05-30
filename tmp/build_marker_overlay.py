#!/usr/bin/env python3
"""Build a TINY cpio with just a marker file to test whether the overlay
gets unpacked at all."""
import os, shutil, subprocess

ROOT = "/home/tim/local/gwifi/depthcharge-ipq4019"
OUT = f"{ROOT}/tmp/openwrt-marker-overlay.cpio"
STAGE = f"{ROOT}/tmp/marker-stage"

if os.path.exists(STAGE):
    shutil.rmtree(STAGE)
os.makedirs(f"{STAGE}/etc")
with open(f"{STAGE}/etc/overlay-marker", "w") as f:
    f.write("THIS-FILE-EXISTS-IF-INITRD-UNPACKED\n")

paths = ["etc", "etc/overlay-marker"]
proc = subprocess.run(
    ["cpio", "-o", "-H", "newc", "--owner=0:0"],
    cwd=STAGE, input="\n".join(paths).encode(), capture_output=True,
)
print("cpio stderr:", proc.stderr.decode())
with open(OUT, "wb") as f:
    f.write(proc.stdout)
print(f"Wrote {OUT} ({len(proc.stdout)} bytes)")
ls = subprocess.run(["cpio", "-itv"], input=proc.stdout, capture_output=True)
print(ls.stdout.decode())

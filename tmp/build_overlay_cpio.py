#!/usr/bin/env python3
"""Build a cpio newc archive containing the patched ath10k_pci.ko at
/lib/modules/6.12.74/ath10k_pci.ko. The Linux kernel unpacks initramfs
cpio archives over the existing rootfs at boot time, so files in this
archive REPLACE files of the same path in the embedded initramfs.

Output: tmp/openwrt-gale-overlay.cpio
"""
import os, struct, time, subprocess

ROOT = "/home/tim/local/gwifi/depthcharge-ipq4019"
SRC_KO = f"{ROOT}/tmp/ath10k_pci-patched.ko"
OUT = f"{ROOT}/tmp/openwrt-gale-overlay.cpio"
ARC_PATH = "lib/modules/6.12.74/ath10k_pci.ko"

# Build a staging directory then use the system cpio to create the
# archive. Simpler than hand-rolling the newc format.
STAGE = f"{ROOT}/tmp/overlay-stage"
import shutil
if os.path.exists(STAGE):
    shutil.rmtree(STAGE)
os.makedirs(f"{STAGE}/lib/modules/6.12.74")
shutil.copy(SRC_KO, f"{STAGE}/{ARC_PATH}")
# Also create lib/ and lib/modules/ as directories so cpio includes them
os.makedirs(f"{STAGE}/lib", exist_ok=True)

# Stage the file list
paths = [
    "lib",
    "lib/modules",
    "lib/modules/6.12.74",
    "lib/modules/6.12.74/ath10k_pci.ko",
]
# Write file list to a temp file
list_path = f"{STAGE}/.cpio-list"
with open(list_path, "w") as f:
    for p in paths:
        f.write(p + "\n")

# Run cpio -o -H newc < list > out, with cwd at stage
proc = subprocess.run(
    ["cpio", "-o", "-H", "newc", "--reproducible"],
    cwd=STAGE,
    input="\n".join(paths).encode(),
    capture_output=True,
)
print("cpio stderr:", proc.stderr.decode()[-500:])
if proc.returncode != 0:
    raise SystemExit(f"cpio failed with {proc.returncode}")

with open(OUT, "wb") as f:
    f.write(proc.stdout)

print(f"Wrote {OUT} ({len(proc.stdout)} bytes)")
print(f"Contains: {ARC_PATH} (size {os.path.getsize(SRC_KO)})")

# Verify by listing
ls = subprocess.run(["cpio", "-itv", "--quiet"], input=proc.stdout, capture_output=True)
print("=== Archive contents ===")
print(ls.stdout.decode())

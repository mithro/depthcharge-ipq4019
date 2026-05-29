#!/usr/bin/env python3
"""Build v19 image: v4 base + newer netboot.elf (with v19 diagnostics) in
FW_MAIN_A/B, re-signed with devkeys. Output: tmp/gale-netboot-v20.bin

v19 adds: GCC ARES probe + clear, MDIO controller readback liveness check.
"""
import subprocess, shutil, sys, os, hashlib, struct

ROOT = "/home/tim/local/gwifi/depthcharge-ipq4019"
CB   = f"{ROOT}/coreboot/util/cbfstool/cbfstool"
FU   = f"{ROOT}/vboot_reference/build/futility/futility"
DK   = f"{ROOT}/vboot_reference/tests/devkeys"
ELF  = f"{ROOT}/depthcharge/build/netboot.elf"
BASE = f"{ROOT}/tmp/gale-netboot-v19.bin"   # use v4 as base; falls back if missing
STOCK = "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"
OUT  = f"{ROOT}/tmp/gale-netboot-v20.bin"


def run(args, **kw):
    print("  $", " ".join(str(a) for a in args)[:200])
    r = subprocess.run(args, capture_output=True, text=True, **kw)
    out = (r.stdout + r.stderr).strip()
    if out:
        for ln in out.splitlines()[-4:]:
            print("    ", ln)
    if r.returncode != 0:
        print("  !! exit", r.returncode)
        sys.exit(1)
    return out


print(f"[1] copy {os.path.basename(BASE)} -> {os.path.basename(OUT)}")
shutil.copy(BASE, OUT)

print(f"[2] swap fallback/payload (new netboot.elf) in FW_MAIN_A and FW_MAIN_B")
for region in ("FW_MAIN_A", "FW_MAIN_B"):
    run([CB, OUT, "remove", "-r", region, "-n", "fallback/payload"])
    run([CB, OUT, "add-payload", "-r", region, "-n", "fallback/payload",
         "-f", ELF, "-c", "lzma"])

print(f"[3] futility sign --type bios (re-signs both VBLOCKs with dev keys)")
run([FU, "sign", "--type", "bios",
     "-s", f"{DK}/firmware_data_key.vbprivk",
     "-b", f"{DK}/firmware.keyblock",
     "-k", f"{DK}/kernel_subkey.vbpubk",
     "-S", f"{DK}/dev_firmware_data_key.vbprivk",
     "-B", f"{DK}/dev_firmware.keyblock",
     "-v", "1",
     OUT])

print(f"[4] verify invariants")
d = open(OUT, "rb").read()
gbb_flags = struct.unpack("<I", d[0x30100c:0x301010])[0]
assert gbb_flags == 0x09, f"GBB flags drifted: 0x{gbb_flags:08x}"
print(f"   GBB flags 0x{gbb_flags:08x} OK")
st = open(STOCK, "rb").read()
assert hashlib.sha256(d[0:0x300000]).digest() == hashlib.sha256(st[0:0x300000]).digest(), \
    "COREBOOT differs from stock"
print(f"   COREBOOT byte-identical to stock OK")

print(f"[5] futility show — body verification")
out = run([FU, "show", OUT])

print(f"\noutput: {OUT}  size={os.path.getsize(OUT)}  sha256={hashlib.sha256(d).hexdigest()}")

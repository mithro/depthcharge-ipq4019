#!/usr/bin/env python3
"""Build a devkey-resigned 8 MiB gale firmware with my netboot depthcharge as
the RW payload (Approach A). Produces tmp/gale-netboot-resigned.bin; no HW write."""
import subprocess, shutil, sys, os

ROOT = "/home/tim/local/gwifi/depthcharge-ipq4019"
CB = f"{ROOT}/coreboot/util/cbfstool/cbfstool"
FU = f"{ROOT}/vboot_reference/build/futility/futility"
DK = f"{ROOT}/vboot_reference/tests/devkeys"
ELF = f"{ROOT}/depthcharge/build/netboot.elf"
STOCK = "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"
OUT = f"{ROOT}/tmp/gale-netboot-resigned.bin"

def run(args, **kw):
    print("  $", " ".join(str(a) for a in args))
    r = subprocess.run(args, capture_output=True, text=True, **kw)
    out = (r.stdout + r.stderr).strip()
    if out:
        for ln in out.splitlines()[-6:]:
            print("    ", ln)
    if r.returncode != 0:
        print("  !! exit", r.returncode); sys.exit(1)
    return out

print("[1] copy stock -> resigned.bin")
shutil.copy(STOCK, OUT)

print("[2] swap fallback/payload -> netboot depthcharge in FW_MAIN_A and B")
for region in ("FW_MAIN_A", "FW_MAIN_B"):
    run([CB, OUT, "remove", "-r", region, "-n", "fallback/payload"])
    run([CB, OUT, "add-payload", "-r", region, "-n", "fallback/payload",
         "-f", ELF, "-c", "lzma"])

print("[3] futility sign --type bios (devkeys)")
run([FU, "sign", "--type", "bios",
     "-s", f"{DK}/firmware_data_key.vbprivk",
     "-b", f"{DK}/firmware.keyblock",
     "-k", f"{DK}/kernel_subkey.vbpubk",
     "-S", f"{DK}/dev_firmware_data_key.vbprivk",
     "-B", f"{DK}/dev_firmware.keyblock",
     "-v", "1",
     OUT])

print("[4] set GBB rootkey -> devkey, flags = 0x28 (force-dev + disable-rollback)")
run([FU, "gbb_utility", "--set", f"--rootkey={DK}/root_key.vbpubk", "--flags=0x28", OUT])

print("[5] verify signatures")
out = run([FU, "show", OUT])
print("\n=== summary ===")
print("output:", OUT, os.path.getsize(OUT), "bytes")

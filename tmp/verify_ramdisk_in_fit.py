#!/usr/bin/env python3
"""Verify the ramdisk inside our FIT decompresses correctly."""
import libfdt, gzip, sys

src = sys.argv[1] if len(sys.argv) > 1 else "tmp/openwrt-gale-patched.itb"
fit = libfdt.Fdt(open(src, "rb").read())
images = fit.subnode_offset(0, "images")
rd = fit.subnode_offset(images, "ramdisk-1")
rd_data = bytes(fit.getprop(rd, "data"))
print(f"Ramdisk in FIT: {len(rd_data)} bytes")
print(f"First 16 bytes: {rd_data[:16].hex()}")
print(f"Last  16 bytes: {rd_data[-16:].hex()}")

try:
    decompressed = gzip.decompress(rd_data)
    print(f"\nDecompressed OK: {len(decompressed)} bytes")
    print(f"Decompressed first 32 bytes: {decompressed[:32].hex()}")
    if decompressed[:6] == b"070701":
        print("=> Looks like cpio newc magic at start")
except Exception as e:
    print(f"\ngzip err: {e}")

#!/usr/bin/env python3
"""Extract the raw FIT from a .itb.vboot ChromeOS vboot-wrapper.
The vboot wrapper has its raw FIT at file offset 0x10000."""
import sys, os

src = sys.argv[1]
dst = sys.argv[2] if len(sys.argv) > 2 else src.replace(".itb.vboot", ".itb")

with open(src, "rb") as f:
    f.seek(0x10000)
    raw = f.read()
# Strip trailing zero padding to find the actual FIT end
while raw and raw[-1] == 0:
    raw = raw[:-1]
# FIT (fdt) has a header with totalsize at offset 4 (big-endian u32)
import struct
totalsize = struct.unpack(">I", raw[4:8])[0]
fit = raw[:totalsize]
with open(dst, "wb") as f:
    f.write(fit)
print(f"  raw at 0x10000, totalsize=0x{totalsize:x} ({len(fit)} B)")
print(f"  wrote {dst}")

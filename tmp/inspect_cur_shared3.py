#!/usr/bin/env python3
"""Check BOTH offset 0 and offset 0x550000 in the flashrom 1.4 read file."""
d = open("/home/tim/local/gwifi/depthcharge-ipq4019/tmp/cur-shared2.bin", "rb").read()
print(f"file size: {len(d)}")
for off, label in [(0, "file offset 0"), (0x550000, "file offset 0x550000")]:
    chunk = d[off:off+64]
    print(f"\n--- {label} ---")
    print(f"hex: {chunk.hex()}")
    print(f"text: {chunk.decode('latin1', 'replace')}")

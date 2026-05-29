#!/usr/bin/env python3
"""Compare SuzyQ-read dump against v3.bin (last CH341A flash) by region.
Static regions (COREBOOT, FMAP, FW_MAIN_A, VBLOCK_A) should match.
Dynamic regions (RW_NVRAM, RW_VPD, RW_GPT) may differ from boot writes."""
import hashlib

dump = open("/home/tim/local/gwifi/depthcharge-ipq4019/tmp/correct_suzyq_dump.bin", "rb").read()
v3   = open("/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-netboot-v3.bin", "rb").read()
stock = open("/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin", "rb").read()

# gale FMAP regions (from prior session knowledge)
REGIONS = [
    ("BOOT_STUB",      0x000000, 0x300000),   # = COREBOOT (the RO region)
    ("FMAP",           0x3F0000, 0x000800),   # FMAP descriptor
    ("GBB",            0x300000, 0x040000),   # GBB
    ("RW_SECTION_A",   0x400000, 0x1F8000),   # full RW slot A
    ("VBLOCK_A",       0x400000, 0x010000),
    ("FW_MAIN_A",      0x410000, 0x1E8000),
    ("RW_SECTION_B",   0x600000, 0x1F8000),   # full RW slot B
    ("VBLOCK_B",       0x600000, 0x010000),
    ("FW_MAIN_B",      0x610000, 0x1E8000),
    ("RW_NVRAM",       0x7F0000, 0x004000),   # may differ from flash
    ("RW_VPD",         0x7F4000, 0x002000),   # may differ
    ("RO_VPD",         0x3FF000, 0x001000),
]

def sha(b): return hashlib.sha256(b).hexdigest()[:16]

print(f"{'Region':16s} {'len':>8s}  {'dump':>16s}  {'v3':>16s}  {'stock':>16s}  match?")
for name, off, l in REGIONS:
    d = dump[off:off+l]
    v = v3[off:off+l]
    s = stock[off:off+l]
    m_v3   = "v3=match" if d == v else ".."
    m_stock = "stock=match" if d == s else ".."
    print(f"{name:16s} {l:>8d}  {sha(d):>16s}  {sha(v):>16s}  {sha(s):>16s}  {m_v3} {m_stock}")

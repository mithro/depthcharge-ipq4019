#!/usr/bin/env python3
"""Patch ath10k_pci.ko to neutralize the FEPLL_PLL_DIV read +
WIFI_SCRATCH_5_REG write sequence that triggers the imprecise external
abort in netboot context.

In the disassembly:

  4d90:  e5953668   ldr r3, [r5, #1640]     # r3 = ar_ahb->gcc_mem
  4d94:  e2833a2f   add r3, r3, #0x2f000    # r3 += 0x2F000
  4d98:  e5932020   ldr r2, [r3, #32]       # r2 = *(r3+0x20) = FEPLL_PLL_DIV ← faults
  4d9c:  f57ff04f   dsb sy
  4da0:  e5953660   ldr r3, [r5, #1632]     # r3 = ar_ahb->mem (wifi reg base)
  4da4:  e2833a4f   add r3, r3, #0x4f000    # r3 += 0x4F000
  4da8:  e2833014   add r3, r3, #20         # r3 += 0x14
  4dac:  f57ff04e   dsb st
  4db0:  e5832000   str r2, [r3]            # *(mem+0x4F014) = r2 (WIFI_SCRATCH_5)

We patch this whole sequence to NOPs (mov r0, r0 = 0xe1a00000) so probe
continues without panicking. WIFI_SCRATCH_5 not being set with FEPLL
divider should be benign on a freshly-booted gale (the chip uses default
divider values from boot).

The .text section starts at file offset 0x34 (per readelf). So in the
file, the instructions to patch are at file offset 0x34 + 0x4d90 = 0x4dc4
through 0x4db3 (inclusive, ~9 instructions of 4 bytes = 36 bytes).
"""
import struct, sys, hashlib

SRC = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/ath10k_pci.ko"
DST = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/ath10k_pci-patched.ko"

# Section .text starts at file offset 0x34 per readelf.
TEXT_OFFSET_IN_FILE = 0x34
# Patch starts at .text offset 0x4d90 (the ldr r3, [r5, #1640]).
PATCH_TEXT_OFFSET = 0x4d90
# Patch length: 9 instructions = 0x24 bytes (0x4d90 through 0x4db3).
PATCH_LEN_INSTRS = 9

NOP = struct.pack("<I", 0xe1a00000)  # mov r0, r0

with open(SRC, "rb") as f:
    data = bytearray(f.read())

print(f"Source size: {len(data)} bytes")
print(f"SHA256: {hashlib.sha256(data).hexdigest()}")

# Verify expected instructions are at the patch target
file_off = TEXT_OFFSET_IN_FILE + PATCH_TEXT_OFFSET
expected = [
    0xe5953668,  # ldr r3, [r5, #1640]
    0xe2833a2f,  # add r3, r3, #0x2f000
    0xe5932020,  # ldr r2, [r3, #32]
    0xf57ff04f,  # dsb sy
    0xe5953660,  # ldr r3, [r5, #1632]
    0xe2833a4f,  # add r3, r3, #0x4f000
    0xe2833014,  # add r3, r3, #20
    0xf57ff04e,  # dsb st
    0xe5832000,  # str r2, [r3]
]
print(f"\nVerifying instructions at file offset 0x{file_off:x}:")
ok = True
for i, exp in enumerate(expected):
    actual = struct.unpack_from("<I", data, file_off + i*4)[0]
    mark = "OK" if actual == exp else "MISMATCH"
    print(f"  +{i:2d} *4: 0x{actual:08x}  expected 0x{exp:08x}  {mark}")
    if actual != exp:
        ok = False
if not ok:
    sys.exit("Disassembly mismatch — refusing to patch")

# Patch — replace all 9 instructions with NOPs
print(f"\nPatching {PATCH_LEN_INSTRS} instructions to NOPs at file 0x{file_off:x}")
for i in range(PATCH_LEN_INSTRS):
    struct.pack_into("<I", data, file_off + i*4, 0xe1a00000)

# Verify
print(f"\nAfter patch:")
for i in range(PATCH_LEN_INSTRS):
    actual = struct.unpack_from("<I", data, file_off + i*4)[0]
    print(f"  +{i:2d} *4: 0x{actual:08x}")

with open(DST, "wb") as f:
    f.write(data)
print(f"\nWrote {DST}")
print(f"SHA256: {hashlib.sha256(data).hexdigest()}")

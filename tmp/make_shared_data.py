#!/usr/bin/env python3
"""Build a depthcharge netboot_params blob containing
   NetbootParamIdKernelArgs = "modprobe.blacklist=ath10k_pci,ath10k_ahb"
and write it as a fresh 8 MiB image with ONLY the SHARED_DATA
(0x550000–0x560000) region populated. The rest stays at 0xff so
flashrom --fmap --image SHARED_DATA will only update that region.

Format of the netboot params blob (depthcharge/src/netboot/params.c):

  bytes  0..7   : "netboot\0"           (sizeof(netboot_sig) = 8)
  bytes  8..11  : count (u32 LE)        (number of params)
  for each param:
      u32 type, u32 size, <size> bytes of data, padded to u32 boundary

NetbootParamId values (params.h):
  TftpServerIp = 1
  KernelArgs   = 2
  Bootfile     = 3
  ArgsFile     = 4
"""
import struct, sys, os

STOCK = "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"
OUT   = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-shared-data-v22.bin"

SHARED_OFF  = 0x550000
SHARED_SIZE = 0x10000   # 64 KB (from FMAP)
FLASH_SIZE  = 0x800000  # 8 MiB W25Q64

# `init=/bin/sh` escapes procd entirely so kmodloader never runs and we
# get a raw busybox shell at PID 1. From there we can manually inspect
# /sys/firmware, /proc/kallsyms, /lib/modules and decide what to do
# about the ath10k_pci probe oops (which kills the kernel because
# OpenWrt builds with CONFIG_PANIC_ON_OOPS=y).
KERNEL_ARGS = b"init=/bin/sh\x00"

NETBOOT_SIG = b"netboot\x00"   # sizeof("netboot") in C includes NUL = 8

def pad32(b):
    """Pad to multiple of 4 bytes with NULs."""
    rem = (-len(b)) & 3
    return b + b"\x00" * rem

blob = bytearray()
blob += NETBOOT_SIG                              # 8 bytes
blob += struct.pack("<I", 1)                     # count = 1
# param[0]: type=KernelArgs(2), size, data
data = pad32(KERNEL_ARGS)
blob += struct.pack("<I", 2)                     # type = KernelArgs
blob += struct.pack("<I", len(KERNEL_ARGS))      # size = unpadded length
blob += data                                     # padded data

assert len(blob) <= SHARED_SIZE, f"blob {len(blob)} > SHARED_DATA {SHARED_SIZE}"
print(f"params blob: {len(blob)} bytes")
print(f"  hex: {blob.hex()}")

# Read stock to keep RO/RW regions identical; only patch SHARED_DATA
with open(STOCK, "rb") as f:
    img = bytearray(f.read())
assert len(img) == FLASH_SIZE, f"stock size {len(img)} != {FLASH_SIZE}"

# Replace SHARED_DATA region: blob + 0xff fill (matches erased flash, which
# is what flashrom expects to write; SHARED_DATA was all 0x00 in stock but
# the blob+pad pattern is what we want NOW).
new_shared = bytearray(b"\xff" * SHARED_SIZE)
new_shared[: len(blob)] = blob
img[SHARED_OFF : SHARED_OFF + SHARED_SIZE] = new_shared

with open(OUT, "wb") as f:
    f.write(img)

# Sanity: nothing else changed. Note SHARED_DATA (0x550000–0x560000) is
# *inside* RW_SECTION_A's range, but it's NOT covered by VBLOCK_A's hash
# over FW_MAIN_A (RW_SHARED is by definition scratch). So we check the
# pieces of RW_SECTION_A that come BEFORE SHARED_DATA only.
with open(STOCK, "rb") as f:
    s = f.read()
ranges_unchanged = [
    ("COREBOOT/RO",         0x000000, 0x300000),
    ("GBB",                 0x301000, 0x0DEF00),
    ("VBLOCK_A+FW_MAIN_A+FWID_A",
                            0x400000, 0x550000 - 0x400000),
    ("RW_GPT_PRIMARY",      0x560000, 0x010000),
    ("RW_GPT_SECONDARY",    0x570000, 0x010000),
    ("RW_SECTION_B",        0x580000, 0x160000),
    ("RW_VPD",              0x6E0000, 0x008000),
]
for nm, off, sz in ranges_unchanged:
    if img[off:off+sz] != s[off:off+sz]:
        sys.exit(f"!! region {nm} (0x{off:06x}+0x{sz:x}) unexpectedly modified")
    print(f"  {nm} (0x{off:06x}+0x{sz:x}) byte-identical to stock OK")

print(f"\nwrote {len(img)} bytes to {OUT}")
print(f"size on disk = {os.path.getsize(OUT)}")

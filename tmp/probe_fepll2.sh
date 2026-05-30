#!/bin/sh
# Read physical addresses via /dev/mem using dd. Each read is one 32-bit
# word at the given byte offset.
read_word() {
    name="$1"; addr="$2"
    # /dev/mem dd read using skip in bytes (bs=1)
    # Note: skip needs to be in bs units, so bs=1 means skip=bytes.
    out=$(dd if=/dev/mem bs=4 count=1 skip=$((addr / 4)) 2>&1 | od -An -tx4 -N 4 | head -1 | tr -d ' ')
    echo "  $name @ 0x$(printf '%08x' "$addr") = 0x$out"
}
echo "=== read various GCC offsets ==="
read_word "GCC base"        0x01800000
read_word "GCC+0x10"        0x01800010
read_word "GCC+0x12000 (ESS_CBCR per depthcharge)"  0x01812000
read_word "GCC+0x2F000"     0x0182F000
read_word "GCC+0x2F020 FEPLL_PLL_DIV (panic addr)"  0x0182F020
read_word "GCC+0x3000 (general AHB)"                0x01803000
read_word "GCC+0x1F000 wcss2g_clk_src"              0x0181F000
read_word "GCC+0x20000 wcss5g_clk_src"              0x01820000

#!/bin/sh
# Find what symbol is at offset 0x7000 inside ath10k_pci.ko (the panic LR).
# Also look at offsets near it for context.

echo "=== whoami / tools ==="
which nm objdump readelf
ls /lib/modules/6.12.74/ath10k_pci.ko 2>&1
ls /lib/modules/6.12.74/ 2>&1 | head -20

echo
echo "=== readelf - text section start ==="
readelf -S /lib/modules/6.12.74/ath10k_pci.ko 2>&1 | head -30

echo
echo "=== nm closest symbols to offset 0x7000 ==="
# nm prints addresses as offsets into the .ko's text section
nm /lib/modules/6.12.74/ath10k_pci.ko 2>&1 | awk '$2 ~ /[tT]/' | sort -k1 | awk 'BEGIN{prev=""} {cur=$1; if (cur > "00006d00" && cur < "00007300") print $0; prev=$0}' | head -40

echo
echo "=== nm symbols 0x4000-0x9000 ==="
nm /lib/modules/6.12.74/ath10k_pci.ko 2>&1 | awk '$2 ~ /[tT]/' | sort -k1 | awk '$1 > "00004000" && $1 < "00009000"' | head -50

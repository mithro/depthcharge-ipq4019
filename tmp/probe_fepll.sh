#!/bin/sh
# From gale shell: try reading GCC+0x2F020 (FEPLL_PLL_DIV) directly
# via /dev/mem. Also list /proc/iomem to see what owns GCC.
echo "=== /proc/iomem ==="
cat /proc/iomem 2>&1 | head -50
echo
echo "=== devmem availability ==="
which devmem busybox 2>&1
busybox 2>&1 | grep -o devmem | head -1
echo
echo "=== try reading FEPLL_PLL_DIV via devmem ==="
busybox devmem 0x1802f020 2>&1 || echo "(failed)"
echo
echo "=== try reading early GCC reg (should always succeed) ==="
busybox devmem 0x1800000 2>&1 || echo "(failed)"
echo
echo "=== read GCC at offset 0x10 (general config?) ==="
busybox devmem 0x1800010 2>&1 || echo "(failed)"
echo
echo "=== read at offset 0x2f000 (FEPLL block start?) ==="
busybox devmem 0x182f000 2>&1 || echo "(failed)"
echo
echo "=== read at 0x182f020 directly ==="
busybox devmem 0x182f020 2>&1 || echo "(failed)"

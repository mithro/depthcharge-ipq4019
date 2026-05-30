#!/bin/sh
# After dd, examine partitions to find kernel + rootfs.
echo "=== /proc/partitions ==="
cat /proc/partitions
echo
echo "=== GPT entries via printf-hexdump of mmcblk0 LBA 1+ ==="
# GPT header is at LBA 1
dd if=/dev/mmcblk0 bs=512 skip=1 count=1 2>/dev/null | hexdump -C | head -10
echo
echo "=== first bytes of each partition (to identify type) ==="
for n in 1 2 3 4 5 8 9 10 11 12; do
    echo "--- mmcblk0p$n head ---"
    head -c 32 /dev/mmcblk0p$n 2>/dev/null | hexdump -C | head -3
done
echo
echo "=== blkid (if available) ==="
blkid 2>&1 | head -20
echo
echo "=== /etc/init.d/ list ==="
ls /etc/init.d/ 2>&1 | head -20

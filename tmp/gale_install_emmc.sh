#!/bin/sh
# Run on gale via ssh. Discovers eMMC, inspects partitions, and (if a
# factory.bin is already at /tmp/factory.bin) writes it to /dev/mmcblk0.
echo "=== mmc info ==="
ls /dev/mmcblk0* 2>&1
echo
echo "=== fdisk -l /dev/mmcblk0 ==="
fdisk -l /dev/mmcblk0 2>&1 | head -25
echo
echo "=== /proc/partitions ==="
cat /proc/partitions 2>&1
echo
echo "=== current MBR/GPT layout ==="
head -c 512 /dev/mmcblk0 | hexdump -C | head -5
echo
echo "=== check if /tmp/factory.bin exists ==="
ls -la /tmp/factory.bin 2>&1
echo
echo "=== free space in /tmp (where we'll stage the image) ==="
df -h /tmp 2>&1
echo
echo "=== mem available ==="
free -h

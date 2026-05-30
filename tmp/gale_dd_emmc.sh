#!/bin/sh
# Run on gale via ssh: dd the staged factory.bin to /dev/mmcblk0.
# This replaces the entire eMMC contents (overwrites the existing
# ChromeOS partitions). After reboot, depthcharge should detect the
# new OpenWrt kernel partition layout and boot from it.
set -e
echo "=== verify image ==="
ls -la /root/openwrt-factory.bin
md5sum /root/openwrt-factory.bin
echo
echo "=== unmount any mounted partitions ==="
for p in /dev/mmcblk0p*; do
    mountpoint -q "$p" 2>/dev/null && umount "$p" 2>&1 || true
done
echo
echo "=== dd to /dev/mmcblk0 ==="
dd if=/root/openwrt-factory.bin of=/dev/mmcblk0 bs=1M conv=fsync 2>&1
echo "DD complete"
echo
echo "=== sync ==="
sync
sync
sync
echo
echo "=== verify by reading first 512 bytes back ==="
dd if=/dev/mmcblk0 bs=512 count=1 2>/dev/null | hexdump -C | head -5
echo
echo "=== /proc/partitions after dd (kernel may not have re-read GPT) ==="
cat /proc/partitions
echo
echo "=== READY TO REBOOT — issue 'reboot' from outside the script ==="

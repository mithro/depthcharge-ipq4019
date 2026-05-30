#!/bin/sh
# Replaces /sbin/init in the initramfs. Pivots to /dev/mmcblk0p2
# (OpenWrt squashfs rootfs after factory.bin dd) before procd runs.

exec >/dev/console 2>&1
echo "=== overlay-init: pivot to /dev/mmcblk0p2 ==="

# Bring up basic mounts the initramfs hadn't yet.
[ -d /proc ]    || mkdir -p /proc
[ -d /sys ]     || mkdir -p /sys
mountpoint -q /proc || mount -t proc proc /proc
mountpoint -q /sys  || mount -t sysfs sysfs /sys

# Wait briefly for mmcblk0p2 to appear.
i=0
while [ ! -b /dev/mmcblk0p2 ] && [ "$i" -lt 30 ]; do
    sleep 1
    i=$((i+1))
done

if [ ! -b /dev/mmcblk0p2 ]; then
    echo "!! /dev/mmcblk0p2 not present, dropping to shell"
    exec /bin/sh
fi

mkdir -p /newroot
echo "=== mounting /dev/mmcblk0p2 (squashfs) at /newroot ==="
mount -t squashfs -o ro /dev/mmcblk0p2 /newroot
if [ "$?" != "0" ]; then
    echo "!! squashfs mount failed, dropping to shell"
    exec /bin/sh
fi

echo "=== switch_root /newroot /sbin/init ==="
exec switch_root /newroot /sbin/init
echo "!! switch_root failed, dropping to shell"
exec /bin/sh

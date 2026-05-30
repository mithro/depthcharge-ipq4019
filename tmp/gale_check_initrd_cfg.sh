#!/bin/sh
# What does the running kernel config say about INITRD?
echo "=== /proc/config.gz ==="
ls -la /proc/config.gz 2>&1
echo
zcat /proc/config.gz 2>/dev/null | grep -E "INITRD|INITRAMFS|BLK_DEV_RAM" | head -15
echo
echo "=== /proc/cmdline ==="
cat /proc/cmdline
echo
echo "=== dmesg | initrd ==="
dmesg | grep -iE "initrd|initramfs|cpio" | head -20

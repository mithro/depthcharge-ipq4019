#!/bin/sh
echo "=== /sbin/init ==="
ls -la /sbin/init 2>&1
echo
echo "=== /sbin contents ==="
ls -la /sbin/ 2>&1 | head -20
echo
echo "=== /proc/1/exe ==="
ls -la /proc/1/exe 2>&1
echo
echo "=== /proc/1/comm ==="
cat /proc/1/comm 2>&1
echo
echo "=== Did our overlay get unpacked? Looking for new files ==="
ls -la /tmp/overlay-* 2>&1
ls -la /sbin/init.* 2>&1

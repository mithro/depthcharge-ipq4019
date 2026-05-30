#!/bin/sh
echo "=== /etc/openwrt_release ==="
cat /etc/openwrt_release 2>&1
echo
echo "=== /proc/cmdline ==="
cat /proc/cmdline
echo
echo "=== mount ==="
mount | head
echo
echo "=== ieee80211 phys ==="
ls /sys/class/ieee80211/ 2>&1
echo
echo "=== iwinfo / iw ==="
iw dev 2>&1
echo
echo "=== uci wireless ==="
ls /etc/config/wireless 2>&1
cat /etc/config/wireless 2>&1
echo
echo "=== loaded ath/mac80211 modules ==="
lsmod | grep -iE 'ath|mac80211|cfg80211' | head

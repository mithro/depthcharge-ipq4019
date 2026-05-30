#!/bin/sh
sleep 5
echo "=== iw dev ==="
iw dev
echo
echo "=== ip -br link ==="
ip -br link
echo
echo "=== iwinfo (if avail) ==="
iwinfo 2>&1 | head -25
echo
echo "=== uci get wireless ==="
uci -q export wireless 2>&1 | head -40
echo
echo "=== logread | grep -iE hostapd|wifi|netifd | tail -30 ==="
logread | grep -iE "hostapd|wifi|wlan|netifd|mac80211" | tail -30

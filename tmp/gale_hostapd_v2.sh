#!/bin/sh
# Carefully start hostapd on phy0 (2.4 GHz), no extra messing around.
echo "=== state before ==="
iw phy phy0 info | grep -E "Band|MHz" | head -8

echo "=== add wlan0 on phy0 as AP ==="
iw dev wlan0 del 2>/dev/null
iw phy phy0 interface add wlan0 type __ap 2>&1
ip link set wlan0 up

echo "=== hostapd config ==="
cat > /tmp/hostapd.conf <<'HEOF'
interface=wlan0
driver=nl80211
ssid=GwifiTest
hw_mode=g
channel=6
country_code=US
ieee80211d=1
HEOF

echo "=== run hostapd (foreground, log everything) ==="
hostapd -B /tmp/hostapd.conf -f /tmp/hostapd.log
sleep 4

echo "=== /tmp/hostapd.log ==="
cat /tmp/hostapd.log

echo "=== iw dev ==="
iw dev

echo "=== ip link wlan0 ==="
ip link show wlan0

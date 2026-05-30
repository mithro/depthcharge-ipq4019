#!/bin/sh
killall hostapd wpa_supplicant 2>/dev/null
sleep 1

iw reg set US 2>&1
iw reg get 2>&1 | head -10

iw dev wlan0 del 2>/dev/null
iw phy phy1 interface add wlan0 type __ap 2>&1
ip link set wlan0 up
sleep 1

cat > /tmp/hostapd.conf <<'HEOF'
interface=wlan0
driver=nl80211
ssid=GwifiTest
hw_mode=g
channel=6
HEOF

hostapd /tmp/hostapd.conf 2>&1 &
HPID=$!
sleep 5
echo "=== iw dev ==="
iw dev
echo "=== link state ==="
ip link show wlan0
kill $HPID 2>/dev/null

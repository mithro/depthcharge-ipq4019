#!/bin/sh
killall hostapd wpa_supplicant 2>/dev/null
sleep 1

iw reg set US 2>&1 | head

# wlan0 on phy0 (2.4 GHz radio)
iw dev wlan0 del 2>/dev/null
iw phy phy0 interface add wlan0 type __ap 2>&1
ip link set wlan0 up
sleep 1

cat > /tmp/hostapd.conf <<'HEOF'
interface=wlan0
driver=nl80211
ssid=GwifiTest
hw_mode=g
channel=6
HEOF

hostapd -B /tmp/hostapd.conf 2>&1 | tail -10
sleep 3

echo "=== iw dev ==="
iw dev

echo "=== ip link ==="
ip link show wlan0

echo "=== iw event monitor briefly... ==="
echo "AP status:"
iw dev wlan0 info 2>&1

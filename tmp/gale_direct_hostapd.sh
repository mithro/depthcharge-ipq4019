#!/bin/sh
# Bypass OpenWrt's wifi scripts entirely. Use hostapd directly.
echo "=== stop netifd/hostapd ==="
killall hostapd wpa_supplicant 2>/dev/null
sleep 1

echo "=== iw phy ==="
iw phy phy1 info 2>&1 | head -30

echo "=== create interface phy1-ap manually ==="
iw dev wlan0 del 2>/dev/null
iw phy phy1 interface add wlan0 type managed 2>&1
sleep 1
iw dev wlan0 set type __ap 2>&1
ip link set wlan0 up
ip addr add 192.168.1.1/24 dev wlan0 2>&1 | head -3

echo "=== write hostapd minimal config ==="
cat > /tmp/hostapd.conf <<'HEOF'
interface=wlan0
driver=nl80211
ssid=GwifiTest
hw_mode=g
channel=11
country_code=US
ieee80211d=1
HEOF

echo "=== run hostapd ==="
hostapd -B /tmp/hostapd.conf 2>&1 | tail
sleep 2

echo "=== state ==="
iw dev
ip -br link

echo "=== logread tail (hostapd) ==="
logread | grep -iE "hostapd" | tail -10

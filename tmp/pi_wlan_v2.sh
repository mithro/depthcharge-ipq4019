#!/bin/sh
# Stop NetworkManager from managing wlan0, then connect manually.

echo "=== stop wpa_supplicant (NM) ==="
sudo systemctl stop wpa_supplicant 2>&1
sleep 1
sudo pkill -9 wpa_supplicant 2>/dev/null
sleep 1
sudo pkill -9 -f "dhclient.*wlan0" 2>/dev/null

echo "=== ensure wlan0 is up + unmanaged ==="
sudo nmcli device set wlan0 managed no 2>&1
sudo ip addr flush dev wlan0
sudo ip link set wlan0 down
sleep 1
sudo ip link set wlan0 up
sleep 2

echo "=== fresh wpa_supplicant in foreground briefly ==="
sudo wpa_supplicant -i wlan0 -c /tmp/wpa-gwifi.conf -D nl80211 -B
sleep 5

echo "=== iw link ==="
sudo iw dev wlan0 link

echo "=== assign IP ==="
sudo ip addr add 192.168.1.42/24 dev wlan0
sleep 1

echo "=== ping ==="
ping -c 5 -W 2 -I wlan0 192.168.1.1 2>&1 | tail -8

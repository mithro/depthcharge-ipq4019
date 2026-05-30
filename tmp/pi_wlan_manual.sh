#!/bin/sh
# Connect Pi to GwifiTest using wpa_supplicant directly. Then assign static IP.
echo "=== ensure NM doesn't interfere ==="
sudo nmcli device set wlan0 managed no 2>&1 | tail
sleep 1

echo "=== wpa_supplicant config ==="
cat > /tmp/wpa-gwifi.conf <<'WEOF'
network={
    ssid="GwifiTest"
    key_mgmt=NONE
}
WEOF

echo "=== launch wpa_supplicant ==="
sudo pkill -f "wpa_supplicant.*wlan0" 2>/dev/null
sleep 1
sudo wpa_supplicant -B -i wlan0 -c /tmp/wpa-gwifi.conf -D nl80211 2>&1 | tail
sleep 3

echo "=== add static IP ==="
sudo ip addr add 192.168.1.42/24 dev wlan0 2>/dev/null
ip -br addr show wlan0

echo "=== iw link ==="
sudo iw dev wlan0 link 2>&1 | head -10

echo "=== ping gale ==="
ping -c 3 -W 2 -I wlan0 192.168.1.1 2>&1 | tail -5

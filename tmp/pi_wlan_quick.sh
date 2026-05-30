#!/bin/sh
# Quickly try to connect Pi's wlan0 to GwifiTest, then check.
sudo pkill -9 wpa_supplicant 2>/dev/null
sleep 1
sudo nmcli device set wlan0 managed no 2>&1 | head
sudo ip addr flush dev wlan0
sudo ip link set wlan0 down
sleep 1
sudo ip link set wlan0 up
sleep 1

cat > /tmp/wpa-gwifi.conf <<'WEOF'
ctrl_interface=/run/wpa_supplicant
ctrl_interface_group=root
network={
    ssid="GwifiTest"
    key_mgmt=NONE
    scan_ssid=1
}
WEOF

sudo wpa_supplicant -i wlan0 -c /tmp/wpa-gwifi.conf -D nl80211 -B 2>&1 | tail
sleep 6
echo === wpa_cli status ===
sudo wpa_cli -i wlan0 status | head
echo === iw link ===
sudo iw dev wlan0 link
echo === IP assign + ping ===
sudo ip addr add 192.168.1.42/24 dev wlan0 2>&1 | head
sleep 1
ping -c 3 -W 2 -I wlan0 192.168.1.1 2>&1 | tail

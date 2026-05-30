#!/bin/sh
# Connect Pi's wlan0 to the open AP "GwifiTest"
echo "=== before ==="
ip -br link show wlan0
ip -br addr show wlan0
echo
echo "=== nmcli connect ==="
sudo nmcli device wifi connect 'GwifiTest' --rescan yes 2>&1
sleep 3
echo
echo "=== after ==="
ip -br link show wlan0
ip -br addr show wlan0
echo
echo "=== iw link ==="
iw dev wlan0 link 2>&1
echo
echo "=== ping 192.168.1.1 over wlan0 (gale's br-lan) ==="
sudo ping -c 3 -W 2 -I wlan0 192.168.1.1 2>&1 | tail -8

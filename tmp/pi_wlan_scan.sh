#!/bin/sh
# From the Pi, scan for the gale AP. Pi's built-in wifi is wlan0.
echo "=== Pi wlan0 state ==="
ip -br link show wlan0
echo
echo "=== bring up if needed ==="
sudo nmcli radio wifi on 2>/dev/null
sudo rfkill unblock wifi 2>/dev/null
sudo ip link set wlan0 up
sleep 1
echo
echo "=== scan for GwifiTest ==="
sudo nmcli -t -f BSSID,SSID,CHAN,SIGNAL,SECURITY,RATE device wifi list --rescan yes 2>&1 | head -10 | grep -i "Gwifi\|test\|^[0-9A-F]"
echo
echo "=== or iw scan ==="
sudo iw dev wlan0 scan 2>&1 | grep -B 1 -A 1 "SSID:" | head -30

#!/bin/sh
# Wait for steady state, then configure via OpenWrt's own scripts.
# Add disabled=0 explicitly. Use the ipq40xx default radio name.

# Stop anything that might be interfering.
killall hostapd wpa_supplicant 2>/dev/null
sleep 2

# Find correct radio path for OpenWrt's auto-detection
RADIO0_PATH=$(uci show wireless | grep '\.path=' | head -1)
echo "current radio paths: $RADIO0_PATH"

# Generate the config OpenWrt expects via wifi config command
wifi config 2>/dev/null
echo "=== wireless after auto-gen ==="
cat /etc/config/wireless

echo
echo "=== enabling first radio's ap iface ==="
uci show wireless | head -20
uci set wireless.@wifi-device[0].disabled='0'
uci set wireless.@wifi-iface[0].ssid='GwifiTest'
uci set wireless.@wifi-iface[0].encryption='none'
uci set wireless.@wifi-iface[0].disabled='0'
uci commit wireless

echo
echo "=== wifi reload ==="
wifi 2>&1
sleep 4

echo
echo "=== iw dev ==="
iw dev

echo
echo "=== logread after wifi reload ==="
logread | grep -iE "wifi|hostapd|wlan" | tail -15

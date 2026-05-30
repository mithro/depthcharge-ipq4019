#!/bin/sh
# Update wpa_supplicant config with control interface and proper options

echo "=== kill existing wpa_supplicant ==="
sudo pkill -9 wpa_supplicant 2>/dev/null
sleep 2

cat > /tmp/wpa-gwifi.conf <<'WEOF'
ctrl_interface=/run/wpa_supplicant
ctrl_interface_group=root
network={
    ssid="GwifiTest"
    key_mgmt=NONE
    scan_ssid=1
}
WEOF

echo "=== start wpa_supplicant verbose ==="
sudo wpa_supplicant -i wlan0 -c /tmp/wpa-gwifi.conf -D nl80211 -B -d > /tmp/wpa.log 2>&1
sleep 5
echo "=== status ==="
sudo wpa_cli -i wlan0 status 2>&1 | head -15
echo
echo "=== last 30 lines of wpa.log ==="
tail -30 /tmp/wpa.log

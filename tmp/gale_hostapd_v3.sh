#!/bin/sh
killall hostapd 2>/dev/null; sleep 1
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
country_code=US
ieee80211d=1
HEOF

# Foreground with -dd for debug
hostapd -dd /tmp/hostapd.conf > /tmp/hostapd_out.log 2>&1 &
HPID=$!
sleep 5
echo "=== iw dev (check if AP came up) ==="
iw dev
echo "=== ps grep hostapd ==="
ps w | grep hostapd | grep -v grep
echo "=== last 40 lines of hostapd log ==="
tail -40 /tmp/hostapd_out.log
kill $HPID 2>/dev/null

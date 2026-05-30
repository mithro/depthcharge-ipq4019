#!/bin/sh
# Conservative hostapd config — explicit frequency, no 802.11n
echo "=== killall hostapd and wpa_supplicant ==="
killall hostapd wpa_supplicant 2>/dev/null
sleep 1

# Re-establish wlan0 on phy1 (2.4 GHz radio)
iw dev wlan0 del 2>/dev/null
iw phy phy1 interface add wlan0 type managed 2>&1
iw dev wlan0 set type __ap 2>&1
ip link set wlan0 up

echo "=== hostapd conf ==="
cat > /tmp/hostapd.conf <<'HEOF'
interface=wlan0
driver=nl80211
ssid=GwifiTest
hw_mode=g
channel=6
country_code=US
ieee80211n=0
HEOF

echo "=== hostapd run (foreground briefly) ==="
hostapd /tmp/hostapd.conf 2>&1 &
HPID=$!
sleep 4
echo "=== iw dev ==="
iw dev
echo "=== ip link wlan0 ==="
ip link show wlan0
echo "=== hostapd process ==="
ps w | grep hostapd | grep -v grep | head
echo "=== killing hostapd (started for test) ==="
kill $HPID 2>/dev/null

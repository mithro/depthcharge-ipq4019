#!/bin/sh
echo "=== wireless config ==="
cat /etc/config/wireless 2>&1
echo
echo "=== current phys ==="
ls /sys/class/ieee80211/
iw phy 2>&1 | head -30
echo
echo "=== iw dev ==="
iw dev
echo
echo "=== set test SSID ==="
# Replace wireless config with a simple open AP on the 2.4 GHz radio.
# Per gale's typical OpenWrt naming, radio0 = 5G, radio1 = 2.4G. But
# we test with both.
cat > /etc/config/wireless <<'WEOF'
config wifi-device 'radio0'
	option type 'mac80211'
	option path 'platform/soc/a000000.wifi'
	option channel '36'
	option band '5g'
	option htmode 'VHT80'
	option country 'AU'

config wifi-iface 'default_radio0'
	option device 'radio0'
	option network 'lan'
	option mode 'ap'
	option ssid 'GwifiTest5G'
	option encryption 'none'

config wifi-device 'radio1'
	option type 'mac80211'
	option path 'platform/soc/a800000.wifi'
	option channel '6'
	option band '2g'
	option htmode 'HT20'
	option country 'AU'

config wifi-iface 'default_radio1'
	option device 'radio1'
	option network 'lan'
	option mode 'ap'
	option ssid 'GwifiTest2G'
	option encryption 'none'
WEOF

echo
echo "=== restart wifi ==="
wifi up 2>&1 | head -20
sleep 3
echo
echo "=== iw dev after up ==="
iw dev
echo
echo "=== hostapd status ==="
ps w | grep -E "hostapd|wpa_sup" | grep -v grep
echo
echo "=== scan from gale (sanity) ==="
iw dev phy0-ap0 scan 2>&1 | grep SSID 2>&1 | head

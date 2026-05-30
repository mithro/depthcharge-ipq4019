#!/bin/sh
# Try a minimal wifi config to avoid the band.ht_capa null issue
echo "=== existing /etc/board.d/ and /etc/wireless/ ==="
ls /etc/board.d/ 2>&1 | head
echo
echo "=== wifi config minimal ==="
# Use channel 11 (2.4GHz, widely supported), no HT
cat > /etc/config/wireless <<'WEOF'
config wifi-device 'radio0'
	option type 'mac80211'
	option path 'platform/soc/a800000.wifi'
	option channel '11'
	option band '2g'
	option country 'US'

config wifi-iface 'default_radio0'
	option device 'radio0'
	option network 'lan'
	option mode 'ap'
	option ssid 'GwifiTest'
	option encryption 'none'
WEOF

echo "=== wifi up ==="
wifi up 2>&1 | head -10
sleep 4

echo "=== iw dev ==="
iw dev

echo "=== ip -br addr ==="
ip -br addr

echo "=== logread tail ==="
logread | tail -30

#!/bin/bash
# Set up gale netboot infrastructure on rpi4 with ONLY eth-glan active.
# eth-gwan USB ethernet has already been physically powered OFF via uhubctl.
set -eu
sudo pkill -9 -f dnsmasq-gwifi 2>/dev/null || true
sleep 1
sudo ip link set eth-glan up
sudo ip addr add 10.42.1.1/24 dev eth-glan 2>/dev/null || true
sed 's/^interface=IFACE/interface=eth-glan/' /tmp/dnsmasq-gwifi.conf \
  | sudo tee /tmp/dnsmasq-gwifi.active.conf > /dev/null
sudo rm -f /tmp/dnsmasq-gwifi.log /tmp/dnsmasq-gwifi.leases
sudo dnsmasq --conf-file=/tmp/dnsmasq-gwifi.active.conf
echo "=== uhubctl hub 2 ==="
sudo uhubctl -l 2 2>&1 | head -8
echo "=== ip ==="
ip -br link show | grep -E "eth-"

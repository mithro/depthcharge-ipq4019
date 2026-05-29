#!/bin/bash
# WAN-port test: power off eth-glan USB, power on eth-gwan USB,
# set up dnsmasq on eth-gwan, verify gale only sees PHY 4 link.
set -eu
echo "=== Power off eth-glan USB (hub 2 port 2) ==="
sudo uhubctl -l 2 -p 2 -a off 2>&1 | tail -5
sleep 2
echo "=== Power on eth-gwan USB (hub 2 port 1) ==="
sudo uhubctl -l 2 -p 1 -a on 2>&1 | tail -5
sleep 4
echo "=== uhubctl hub 2 status ==="
sudo uhubctl -l 2 2>&1 | head -8
echo "=== Interfaces ==="
ip -br link show | grep -E "eth-"
echo "=== Configure dnsmasq on eth-gwan ==="
sudo pkill -9 -f dnsmasq-gwifi || true
sleep 1
sudo ip addr flush dev eth-gwan 2>/dev/null || true
sudo ip link set eth-gwan up
sudo ip addr add 10.42.1.1/24 dev eth-gwan
sed 's/^interface=IFACE/interface=eth-gwan/' /tmp/dnsmasq-gwifi.conf \
  | sudo tee /tmp/dnsmasq-gwifi.active.conf > /dev/null
sudo rm -f /tmp/dnsmasq-gwifi.log /tmp/dnsmasq-gwifi.leases
sudo dnsmasq --conf-file=/tmp/dnsmasq-gwifi.active.conf
echo "=== eth-gwan state ==="
sudo ethtool eth-gwan 2>&1 | grep -E "Speed|Link detected"

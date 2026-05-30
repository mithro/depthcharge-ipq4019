#!/bin/sh
# Wait for gale to be reachable via the Pi's LAN-side (eth-glan, 192.168.1.x).
# Re-applies the 192.168.1.10/24 address every loop since NetworkManager
# (or whatever) on the Pi may wipe it after a uhubctl cycle.
sudo ip addr add 192.168.1.10/24 dev eth-glan 2>/dev/null || true
sudo ip link set eth-glan up
while : ; do
  ip addr show eth-glan | grep -q "inet 192.168" || sudo ip addr add 192.168.1.10/24 dev eth-glan 2>/dev/null
  if ping -c 1 -W 1 192.168.1.1 >/dev/null; then
    echo "gale-reachable"
    exit 0
  fi
  sleep 3
done

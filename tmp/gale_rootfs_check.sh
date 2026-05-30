#!/bin/sh
echo "=== mounts ==="
mount | head -20
echo
echo "=== rootfs writability test ==="
touch /test-writable.txt 2>&1 && rm /test-writable.txt && echo "(/) is writable"
echo
echo "=== /lib/modules ==="
ls -la /lib/modules/6.12.74/ath10k* 2>&1
echo
echo "=== rename test ==="
mv /lib/modules/6.12.74/ath10k_pci.ko /lib/modules/6.12.74/ath10k_pci.ko.bak 2>&1 && echo "renamed OK" && mv /lib/modules/6.12.74/ath10k_pci.ko.bak /lib/modules/6.12.74/ath10k_pci.ko && echo "renamed back"

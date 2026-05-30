#!/bin/sh
# Run on gale via ssh. Shell because it's a busybox initramfs (no python).
echo "=== /proc/cmdline ==="
cat /proc/cmdline
echo
echo "=== /sys/firmware/devicetree/base/firmware ==="
ls -la /sys/firmware/devicetree/base/firmware/ 2>&1
echo
echo "=== coreboot DT subnode reg ==="
xxd /sys/firmware/devicetree/base/firmware/coreboot/reg 2>&1
echo
echo "=== coreboot DT subnode compatible ==="
cat /sys/firmware/devicetree/base/firmware/coreboot/compatible 2>&1; echo
echo
echo "=== wifi DT node status (a000000) ==="
cat /sys/firmware/devicetree/base/soc/wifi@a000000/status 2>&1; echo
echo
echo "=== modules in initramfs ==="
ls /etc/modules.d/ 2>&1
echo
echo "=== modules.d/ath* ==="
ls /etc/modules.d/ | grep -i ath
echo
echo "=== firmware/ath10k tree ==="
find /lib/firmware/ath10k -type f 2>&1
echo
echo "=== loaded ath/wifi modules ==="
lsmod | grep -E "ath|mac80211|cfg80211" 2>&1
echo
echo "=== /etc/config/wireless ==="
cat /etc/config/wireless 2>&1 || echo "(no wireless config)"
echo
echo "=== /sys/class/ieee80211 ==="
ls /sys/class/ieee80211/ 2>&1
echo
echo "=== /sys/class/net ==="
ls /sys/class/net/ 2>&1
echo
echo "=== mtd partitions ==="
cat /proc/mtd 2>&1 || echo "(no mtd)"
echo
echo "=== /dev/mtd* ==="
ls -la /dev/mtd* 2>&1
echo
echo "=== /proc/iomem coreboot/cbmem ==="
grep -iE "cbmem|coreboot|wifi" /proc/iomem 2>&1 | head -20

#!/bin/sh
echo "=== /etc/preinit ==="
cat /etc/preinit 2>&1 | head -40
echo
echo "=== /lib/preinit ==="
ls /lib/preinit/ 2>&1
echo
echo "=== /etc/init.d ==="
ls /etc/init.d/ 2>&1
echo
echo "=== /etc/modules.d/ath10k-ct ==="
cat /etc/modules.d/ath10k-ct 2>&1
echo
echo "=== /etc/modules-boot.d/* ==="
ls /etc/modules-boot.d/
for f in /etc/modules-boot.d/*; do
    echo "--- $f ---"
    cat "$f"
done
echo
echo "=== /sys/kernel/debug/clk/clk_summary (FEPLL state) ==="
grep -iE "fepll|wcss|gcc" /sys/kernel/debug/clk/clk_summary 2>&1 | head -40
echo
echo "=== /sys/kernel/debug/clk/clk_dump 2>nothing ==="
head -50 /sys/kernel/debug/clk/clk_summary 2>&1 | head -50

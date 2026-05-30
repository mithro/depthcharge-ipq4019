#!/bin/sh
# Try various ways to map kernel address 0xc06f6174 and module offset 0x7000.
echo "=== /sys/kernel/debug/tracing/available_filter_functions ==="
ls /sys/kernel/debug/tracing/available_filter_functions 2>&1
head -3 /sys/kernel/debug/tracing/available_filter_functions 2>&1
echo
echo "=== /proc/modules ==="
cat /proc/modules | head -10
echo
echo "=== /sys/module/ath10k_pci ==="
ls /sys/module/ath10k_pci/ 2>&1
echo
echo "=== try /proc/$$ /maps ==="
cat /proc/self/maps 2>&1 | head -10
echo
echo "=== sched_debug? ==="
ls /sys/kernel/debug/sched 2>&1 | head -10
echo
echo "=== ftrace lookup for c06f6174 via mcount? ==="
# Look at the addresses register names
ls /sys/kernel/debug/ 2>&1 | head -10
echo
echo "=== try printing symbols via printk %pS ==="
# If we have access to /sys/kernel/debug/dynamic_debug we can pull info
ls /sys/kernel/debug/dynamic_debug/ 2>&1 | head -5
echo
echo "=== look at exception abort handler trace ==="
ls /sys/kernel/notes 2>&1

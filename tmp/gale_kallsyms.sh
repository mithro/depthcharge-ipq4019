#!/bin/sh
# Resolve the addresses from the panic trace via /proc/kallsyms.
# PC was 0xc06f6174, LR pointed inside ath10k_pci+0x7000.
# We also pull the addresses for ath10k_ahb_probe / ath10k_pci_probe
# and the ath10k_pci module base for offset math.

echo "=== module list (ath10k_pci, ath10k_core) ==="
grep -E "^bf|ath10k|^bf[0-9a-f]+" /proc/modules | head -10

echo ""
echo "=== module addresses for ath10k* ==="
cat /sys/module/ath10k_pci/sections/.text 2>&1
cat /sys/module/ath10k_pci/sections/.init.text 2>&1
echo "---"
grep -E " [tT] " /proc/kallsyms | grep -E "ath10k_(ahb|pci)_probe|ath10k_ahb_resource_init|ath10k_ahb_prepare_device|ath10k_ahb_clock_enable|ath10k_ahb_release_reset|ath10k_ahb_gcc_read" | head -20

echo ""
echo "=== resolve panic PCs ==="
# We want kernel symbol nearest to 0xc06f6174 (the panic PC)
# kallsyms format: addr type name
awk '$1 < "c0700000" && $1 > "c06f0000"' /proc/kallsyms | sort | head -30

echo ""
echo "=== regulator / pinctrl / clock symbols near c06* ==="
grep -E " [tT] (regmap_|pinctrl_|clk_core_prepare|qcom_smem|qcom_scm)" /proc/kallsyms | head -10

echo ""
echo "=== dmesg pci/wifi prior to disable ==="
dmesg | grep -iE "ath10k|wifi|pci|coreboot_table|qcom_scm|pinctrl" | head -40

echo ""
echo "=== ath10k_pci module info ==="
modinfo ath10k_pci 2>&1 | head -20

echo ""
echo "=== which probe functions are exported ==="
grep -E " [tT] (ath10k_ahb_init|ath10k_pci_init|ath10k_pci_probe|ath10k_ahb_probe)" /proc/kallsyms

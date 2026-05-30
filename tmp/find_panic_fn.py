#!/usr/bin/env python3
"""Parse the ath10k_pci.ko disassembly to find the function at offset 0x7000
(the panic LR) and the instructions around it.
"""
import re, subprocess

DIS = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/ath10k_pci.dis"
KO  = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/ath10k_pci.ko"

# Regenerate disassembly if missing or older
import os
if not os.path.exists(DIS):
    print("[regenerating disassembly...]")
    with open(DIS, "wb") as out:
        subprocess.run(
            ["arm-linux-gnueabi-objdump", "-d", KO],
            stdout=out, check=True)

funcs = []
with open(DIS) as f:
    for line in f:
        m = re.match(r"^([0-9a-f]{8}) <([^>]+)>:", line)
        if m:
            funcs.append((int(m.group(1), 16), m.group(2)))
funcs.sort()

# Target offsets we want to identify
TARGETS = [0x7000, 0x6e08, 0x6dc, 0x72dc, 0x76dc, 0x70a4, 0x7034, 0x4254, 0x252c, 0x381c, 0x361c]

def fn_for(off):
    cand = None
    for a, n in funcs:
        if a <= off:
            cand = (a, n)
        else:
            break
    return cand

for t in TARGETS:
    a_n = fn_for(t)
    if a_n:
        print(f"  off 0x{t:04x} → fn {a_n[1]} (starts at 0x{a_n[0]:04x}, off+{t-a_n[0]} within)")

# Print disassembly around 0x6e00-0x7100 by parsing every line's address.
print()
print("=== Disassembly around panic LR (0x7000) ===")
WANT_LO, WANT_HI = 0x6e00, 0x7100
with open(DIS) as f:
    for line in f:
        # Function header lines.
        m = re.match(r"^([0-9a-f]{8}) <([^>]+)>:", line)
        if m:
            addr = int(m.group(1), 16)
            if WANT_LO <= addr <= WANT_HI:
                print(line.rstrip())
            continue
        # Per-instruction lines: "    addr:    XX YY ZZ ...   opcode"
        m = re.match(r"^\s+([0-9a-f]+):\s", line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        if WANT_LO <= addr <= WANT_HI:
            print(line.rstrip())

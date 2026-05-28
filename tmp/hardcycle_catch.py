#!/usr/bin/env python3
"""ARM: wait for the gale USB to DISAPPEAR (user is unplugging the adapter),
then wait for it to REAPPEAR (replugged), and IMMEDIATELY hammer flashrom RDID.
Strict policy: NO EC commands — they destroy the post-hard-cycle window.

On detect: print timing, attempt a small forensic read (256B at offset 0 via
layout BOOTBLOCK_4K), and STOP. Do not write — write decisions require user
confirmation."""
import subprocess, time, os, sys
FR = "/usr/sbin/flashrom"
CHIP = "W25Q64BV/W25Q64CV/W25Q64FV"

def present():
    return "18d1:500f" in subprocess.run(["lsusb"], capture_output=True, text=True).stdout

print("[ARMED] Disconnect the gale's POWER ADAPTER now (not the USB).")
print("        Waiting for the gale USB to disappear...")
t0 = time.time()
while time.time() - t0 < 120:
    if not present():
        elapsed = time.time() - t0
        print(f"  → gale USB GONE (after {elapsed:.0f}s)")
        break
    time.sleep(0.5)
else:
    print("[TIMEOUT] gale still present after 120s — aborting.")
    sys.exit(0)

print("\nNow REPLUG the adapter. Waiting for gale to re-enumerate...")
t0 = time.time()
while time.time() - t0 < 60:
    if present():
        elapsed = time.time() - t0
        print(f"  → gale USB BACK (after {elapsed:.0f}s)")
        break
    time.sleep(0.2)
else:
    print("[TIMEOUT] gale did not return — aborting.")
    sys.exit(0)

print("\n[hammering flashrom --flash-name for 30s, NO EC commands]")
t0 = time.time()
attempts = 0; first_detect = None
while time.time() - t0 < 30:
    attempts += 1
    r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-c", CHIP, "--flash-name"],
                       capture_output=True, text=True, timeout=15)
    out = r.stdout + r.stderr
    if r.returncode == 0 and "Winbond" in out:
        elapsed = time.time() - t0
        if first_detect is None:
            first_detect = (attempts, elapsed)
        print(f"  DETECT! attempt {attempts}  t+{elapsed:.2f}s")
        # try a tiny read at offset 0 (4KB sector) for forensic match against stock
        rd = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-c", CHIP,
                             "-r", "tmp/hcc_read.bin",
                             "-l", "tmp/layout.txt", "-i", "BOOTBLOCK_4K"],
                            capture_output=True, text=True, timeout=60)
        print(f"    forensic read rc={rd.returncode}")
        if rd.returncode == 0 and os.path.exists("tmp/hcc_read.bin"):
            d = open("tmp/hcc_read.bin","rb").read()
            # Compare offset 0..0xfff to stock
            STOCK = "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"
            sd = open(STOCK,"rb").read()
            # Note: BOOTBLOCK_4K region is 4KB at offset 0; the read file might be
            # 8MB (whole-chip) with only that 4KB populated, OR 4KB only.
            print(f"    read len={len(d)}")
            # the 4KB at offset 0 of d should match sd[0:0x1000]
            if len(d) >= 0x1000:
                seg = d[:0x1000]
            else:
                seg = d
            matches = sum(1 for a,b in zip(seg, sd[:len(seg)]) if a == b)
            print(f"    match-stock first 4KB: {100*matches/max(len(seg),1):.1f}%")
            print(f"    first 32 bytes (chip): {seg[:32].hex()}")
            print(f"    first 32 bytes (stock):{sd[:32].hex()}")
        print("\n[stopping at first detect — call decision is yours]")
        break

if first_detect is None:
    print(f"\n[no detect in {attempts} attempts, {time.time()-t0:.1f}s]")
    print("RESULT: bus still unresponsive after hard cycle")

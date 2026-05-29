#!/usr/bin/env python3
"""SUPERSEDED — based on a wrong hypothesis. Kept for history only.

The premise here ("if RDID still fails after long VCC removal, the chip is
permanently degraded and CH341A is required") was wrong. The RDID failures
that motivated this probe were caused by the `-c W25Q64BV/W25Q64CV/W25Q64FV`
flag forcing JEDEC ID matching the EC bridge doesn't support — they had
nothing to do with chip degradation. Use the correct SuzyQ procedure
(`gale power off && flashrom -p raiden_debug_spi -r dump.bin`, no `-c`,
no separate probe) — see docs/keeping-suzyq-recovery-working.md.

Original docstring follows:

Single read-only probe: power-cycle once + try flashrom RDID a few times.
Intended to be run after a long period of zero traffic to the device — some
flash chips' status register can self-clear after extended VCC removal."""
import subprocess, time, os
PORT = "/sys/bus/usb/devices/3-0:1.0/usb3-port1/disable"
def present():
    return "18d1:500f" in subprocess.run(["lsusb"], capture_output=True, text=True).stdout
def setdis(v):
    subprocess.run(["sudo","sh","-c",f"echo {v} > {PORT}"], check=True)

print(f"[{time.strftime('%H:%M:%S')}] long-wait probe — single read-only attempt")
print("[cut power]")
setdis(1)
for _ in range(12):
    time.sleep(1)
    if not present(): break
print("[hold 60s with VCC removed]")
time.sleep(60)
print("[restore]")
setdis(0)
t0 = time.time()
detects = 0
for attempt in range(120):  # ~20 seconds
    r = subprocess.run(["sudo","/usr/sbin/flashrom","-p","raiden_debug_spi",
                        "-c","W25Q64BV/W25Q64CV/W25Q64FV","--flash-name"],
                       capture_output=True, text=True, timeout=15)
    if r.returncode == 0 and "Winbond" in (r.stdout + r.stderr):
        elapsed = time.time() - t0
        detects += 1
        print(f"  DETECT! attempt {attempt+1} t+{elapsed:.2f}s")
        if detects >= 3:
            print("[stable detection — chip may be accessible again]")
            break
print(f"[summary: {detects} detects in {attempt+1} attempts over {time.time()-t0:.1f}s]")
if detects == 0:
    print("RESULT: probe returned 0x00 — most likely procedural (this script "
          "uses `-c CHIP` which forces RDID matching the EC bridge does not "
          "support); use the SuzyQ procedure in docs/keeping-suzyq-recovery-working.md")
else:
    print("RESULT: CHIP RESPONDED")

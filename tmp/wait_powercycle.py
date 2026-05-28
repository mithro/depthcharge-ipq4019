#!/usr/bin/env python3
"""Wait for the user to power-cycle the gale: detect the SuzyQ/EC USB device
(18d1:500f) going ABSENT (power cut) then PRESENT (restored)."""
import subprocess, time, os

DEV = "18d1:500f"
BYID = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"

def present():
    r = subprocess.run(["lsusb"], capture_output=True, text=True)
    return DEV in r.stdout.lower() or DEV in r.stdout

t0 = time.time()
TIMEOUT = 600

# Phase A: wait for unplug (absent)
print("waiting for power cut (gale USB to disappear)...", flush=True)
while present() and time.time() - t0 < TIMEOUT:
    time.sleep(1)
if present():
    print("TIMEOUT: gale never disappeared (not power-cycled yet)"); raise SystemExit(0)
print("gale powered off (USB gone) at +%.0fs" % (time.time() - t0), flush=True)

# Phase B: wait for replug (present + stable)
while not present() and time.time() - t0 < TIMEOUT:
    time.sleep(1)
# wait for the by-id node + settle
for _ in range(30):
    if os.path.exists(BYID):
        break
    time.sleep(1)
time.sleep(3)
print("POWER-CYCLE COMPLETE: gale re-enumerated at +%.0fs" % (time.time() - t0), flush=True)

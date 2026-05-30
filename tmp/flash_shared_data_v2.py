#!/usr/bin/env python3
"""Retry flash with EC reboot first to clear stuck SPI state."""
import subprocess, time, serial

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
IMG = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-shared-data-v22.bin"


def ec(cmd, w=1.0, read_back=True):
    s = serial.Serial(EC, 115200, timeout=0.2)
    s.write(b"\r"); time.sleep(0.2)
    try: s.read(8192)
    except Exception: pass
    s.write((cmd + "\r").encode()); time.sleep(w)
    if read_back:
        try:
            print(s.read(4096).decode("latin1", "replace").rstrip(), flush=True)
        except Exception as e:
            print(f"  ec read-back ignored: {e}", flush=True)
    try: s.close()
    except Exception: pass


print("=== EC reboot to clean SPI state ===")
ec("reboot", 4, read_back=False)
# After EC reboot, the USB device re-enumerates briefly.
import os
time.sleep(5)
for _ in range(60):
    if os.path.exists(EC):
        break
    time.sleep(0.5)
time.sleep(2)

print("=== gale power off ===")
ec("gale power off", 2)
time.sleep(2)

print("=== flashrom write SHARED_DATA ===")
r = subprocess.run(
    ["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
     "--fmap", "-w", IMG, "-i", "SHARED_DATA"],
    capture_output=True, text=True, timeout=180)
for ln in (r.stdout + r.stderr).splitlines()[-25:]:
    print(f"  | {ln}")
print(f"exit: {r.returncode}")

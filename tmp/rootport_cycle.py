#!/usr/bin/env python3
"""Power-cycle the gale via the laptop root port (usb3-port1 = the Super Top hub
branch). Confirms the gale USB (18d1:500f) drops and returns."""
import subprocess, time
PORT = "/sys/bus/usb/devices/3-0:1.0/usb3-port1/disable"

def gale_present():
    return "18d1:500f" in subprocess.run(["lsusb"], capture_output=True, text=True).stdout

def setdisable(v):
    subprocess.run(["sudo", "sh", "-c", f"echo {v} > {PORT}"], check=True)

print("before: gale present =", gale_present())
print("cut power (disable usb3-port1)...")
setdisable(1)
for _ in range(12):
    time.sleep(1)
    if not gale_present():
        print("  gale USB DROPPED (power cut confirmed)"); break
else:
    print("  WARNING: gale still present after disable")
print("hold off 5s (flash VCC drains)...")
time.sleep(5)
print("restore power (enable usb3-port1)...")
setdisable(0)
for _ in range(20):
    time.sleep(1)
    if gale_present():
        print("  gale USB RETURNED (powered on)"); break
else:
    print("  WARNING: gale did not return")
print("after: gale present =", gale_present())

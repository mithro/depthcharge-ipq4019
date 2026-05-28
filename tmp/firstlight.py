#!/usr/bin/env python3
"""Reboot the AP and capture the console to see my netboot depthcharge + IPQ4019
driver come up (first light)."""
import time, threading, serial

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"

def openp(path):
    s = serial.Serial(); s.port = path; s.baudrate = 115200; s.timeout = 0.1
    s.dtr = False; s.rts = False; s.open(); return s

cap = []; stop = False
def reader():
    while not stop:
        try:
            s = openp(AP)
            while not stop:
                c = s.read(4096)
                if c: cap.append(c)
        except Exception:
            time.sleep(0.3)
threading.Thread(target=reader, daemon=True).start()

try:
    s = openp(EC); s.write(b"reboot\r"); s.flush(); time.sleep(0.4); s.close()
except Exception as e:
    print("reboot note:", e)
print("[rebooted; capturing AP console 35s]")
time.sleep(35)
stop = True; time.sleep(0.4)

txt = b"".join(cap).decode("latin1", "replace")
print(f"[{sum(len(c) for c in cap)} bytes]")
print("=" * 60)
for ln in txt.splitlines():
    if ln.strip():
        print(ln[:170])

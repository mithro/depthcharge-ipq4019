#!/usr/bin/env python3
"""Enable dev mode via EC, reboot, and capture the AP console to see if a
kernel (OpenWrt) boots from internal storage (breaking the recovery loop)."""
import time, threading, serial

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"

def openp(path, b):
    s = serial.Serial(); s.port = path; s.baudrate = b; s.timeout = 0.1
    s.dtr = False; s.rts = False; s.open(); return s

def ec_cmd(c, wait=1.0):
    s = openp(EC, 115200); s.write((c + "\r").encode()); s.flush(); time.sleep(wait)
    r = s.read(4096); s.close(); return r.decode("latin1", "replace")

print("dev on ->", ec_cmd("gale dev on", 1.0).strip()[-60:])
print("rec off ->", ec_cmd("gale rec off", 1.0).strip()[-60:])
print("gale ->", ec_cmd("gale", 1.0).strip()[-120:])

# capture AP console across an EC reboot
cap = []; stop = False
def reader():
    while not stop:
        try:
            s = openp(AP, 115200)
            while not stop:
                c = s.read(4096)
                if c: cap.append(c)
        except Exception:
            time.sleep(0.3)
threading.Thread(target=reader, daemon=True).start()

print("[reboot EC -> AP boots; capturing 25s]")
try:
    s = openp(EC, 115200); s.write(b"reboot\r"); s.flush(); time.sleep(0.4); s.close()
except Exception as e:
    print("reboot note:", e)
time.sleep(25)
stop = True; time.sleep(0.4)

txt = b"".join(cap).decode("latin1", "replace")
print(f"[AP console {sum(len(c) for c in cap)} bytes]")
for ln in txt.splitlines():
    if ln.strip():
        print(" |", ln[:160])

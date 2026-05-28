#!/usr/bin/env python3
"""Reboot the gale EC (clears latched power state), then capture both consoles."""
import time, threading, serial, os, glob

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"

def openp(path, b):
    s = serial.Serial(); s.port = path; s.baudrate = b; s.timeout = 0.1
    s.dtr = False; s.rts = False; s.open(); return s

# 1) send reboot to EC
try:
    ec = openp(EC, 115200)
    print("[sending EC 'reboot']")
    ec.write(b"reboot\r"); ec.flush(); time.sleep(0.5)
    ec.close()
except Exception as e:
    print("reboot send error:", e)

# 2) wait for re-enumeration
print("[waiting for EC USB re-enumeration]")
for _ in range(40):
    time.sleep(0.5)
    if os.path.exists(EC):
        # ensure it's stable/openable
        try:
            t = openp(EC, 115200); t.close(); break
        except Exception:
            pass
time.sleep(1.0)

# 3) reopen and capture both consoles through the boot
ec_log, ap_log = [], []
stop = False
def rd(path, b, sink):
    while not stop:
        try:
            s = openp(path, b)
            while not stop:
                c = s.read(4096)
                if c: sink.append(c)
        except Exception:
            time.sleep(0.3)
threading.Thread(target=rd, args=(EC,115200,ec_log), daemon=True).start()
threading.Thread(target=rd, args=(AP,115200,ap_log), daemon=True).start()
print("[capturing 18s post-reboot]")
time.sleep(18)
# query power near the end
try:
    e = openp(EC,115200); e.write(b"gale power\r"); e.flush(); time.sleep(1); e.close()
except Exception as ex:
    print("poll err", ex)
time.sleep(1)
stop = True; time.sleep(0.4)

for name, log in (("EC", ec_log), ("AP", ap_log)):
    txt = b"".join(log).decode("latin1","replace")
    print(f"\n===== {name} ({sum(len(c) for c in log)} bytes) =====")
    for ln in txt.splitlines():
        if ln.strip(): print(" |", ln[:160])

#!/usr/bin/env python3
"""Power-cycle the gale AP via EC and capture the AP console from boot."""
import time, threading, serial, sys

baud = int(sys.argv[1]) if len(sys.argv) > 1 else 115200

def openp(port, b):
    s = serial.Serial(); s.port = port; s.baudrate = b; s.timeout = 0.1
    s.dtr = False; s.rts = False; s.open(); return s

ec = openp("/dev/ttyUSB0", 115200)
ap = openp("/dev/ttyUSB1", baud)

cap = []
stop = False
def reader():
    while not stop:
        c = ap.read(4096)
        if c: cap.append(c)
t = threading.Thread(target=reader, daemon=True); t.start()

def ec_cmd(c, wait=1.0):
    ec.reset_input_buffer(); ec.write((c + "\r").encode()); ec.flush(); time.sleep(wait)

print(f"[capturing AP console @ {baud}; power-cycling AP]")
ec_cmd("gale power off", 1.5)
ec_cmd("gale power on", 0.2)
time.sleep(18)            # capture full boot
stop = True; time.sleep(0.3)
ec.close(); ap.close()

data = b"".join(cap)
txt = data.decode("latin1", "replace")
print(f"[captured {len(data)} bytes on AP console]")
print("-" * 60)
print(txt[-6000:] if txt.strip() else "(NO OUTPUT on AP console)")

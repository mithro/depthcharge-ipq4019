#!/usr/bin/env python3
"""Just power gale on via EC."""
import time, serial, os

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"

if not os.path.exists(EC):
    raise SystemExit(f"EC tty missing: {EC}")

s = serial.Serial(EC, 115200, timeout=0.2)
s.write(b"\r"); time.sleep(0.3)
try: s.read(8192)
except Exception: pass

for cmd, wait in [("gale", 1.0), ("gale dev off", 1.0),
                  ("gale rec off", 1.0), ("gale power on", 2.0)]:
    s.write((cmd + "\r").encode()); time.sleep(wait)
    try:
        out = s.read(4096).decode("latin1", "replace")
        print(f"--- {cmd} ---")
        print(out)
    except Exception as e:
        print(f"{cmd}: read err {e}")

s.close()

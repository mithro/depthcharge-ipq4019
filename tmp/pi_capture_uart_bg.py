#!/usr/bin/env python3
"""Capture AP UART continuously to a log file."""
import sys, time, threading, serial, os, datetime
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"
stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
LOG = f"/home/tim/local/gwifi/depthcharge-ipq4019/tmp/ap-uart-{stamp}.log"
DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 120
fp = open(LOG, "wb")
print(f"capturing to {LOG} for {DURATION}s")
print(LOG)  # for caller to pick up
sys.stdout.flush()
t0 = time.time()
while time.time() - t0 < DURATION:
    try:
        s = serial.Serial(AP, 115200, timeout=0.5)
        while time.time() - t0 < DURATION:
            d = s.read(4096)
            if d:
                fp.write(d); fp.flush()
        s.close()
    except Exception as e:
        time.sleep(0.5)
fp.close()
print(f"done ({os.path.getsize(LOG)} bytes)")

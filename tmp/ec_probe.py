#!/usr/bin/env python3
"""Probe the EC for available commands + WP / flash state."""
import time, serial, sys

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"

s = serial.Serial(EC, 115200, timeout=0.3)
s.write(b"\r"); time.sleep(0.2); s.read(8192)

for cmd in ["help", "gale", "flash", "flashinfo", "wp", "rw", "syslock",
            "spi", "ccd"]:
    s.write((cmd + "\r").encode())
    time.sleep(0.6)
    out = s.read(8192).decode("latin1", "replace").rstrip()
    print(f"--- {cmd} ---")
    print(out[:2000])
    print()
s.close()

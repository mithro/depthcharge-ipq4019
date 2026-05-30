#!/usr/bin/env python3
"""Probe EC commands related to flash/wp."""
import time, serial

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
s = serial.Serial(EC, 115200, timeout=0.3)
s.write(b"\r"); time.sleep(0.2); s.read(8192)

for cmd in ["flashwp", "help flashwp", "help gale", "help spixfer",
            "gale dev", "version", "sysinfo", "gpioget GPIO_WP",
            "gpioget AP_FLASH_WP_L"]:
    s.write((cmd + "\r").encode()); time.sleep(0.7)
    out = s.read(8192).decode("latin1", "replace").rstrip()
    print(f"--- {cmd} ---")
    print(out[:1500])
    print()
s.close()

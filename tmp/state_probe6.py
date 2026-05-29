#!/usr/bin/env python3
"""Discover EC commands related to SPI/flash, and check if there's
something we're missing in how the EC bridge activates."""
import subprocess, time, serial

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"

def ec_cmd(cmd, wait=1.0):
    s = serial.Serial()
    s.port = EC; s.baudrate = 115200; s.timeout = 0.2
    s.dtr = False; s.rts = False
    s.open()
    s.write(b"\r"); time.sleep(0.2); s.read(8192)
    s.write((cmd + "\r").encode()); s.flush()
    time.sleep(wait)
    out = s.read(32768).decode("latin1", "replace")
    s.close()
    return out

print("=== EC help (list all commands) ===")
print(ec_cmd("help", wait=2.0))

print()
print("=== EC help on flash ===")
print(ec_cmd("help flash", wait=1.0))

print()
print("=== EC help on spi ===")
print(ec_cmd("help spi", wait=1.0))

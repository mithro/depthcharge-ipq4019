#!/usr/bin/env python3
"""Check flashinfo/flashwp/syslock/spixfer/rw + try raiden flashrom with verbose output."""
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

for cmd in ["help gale", "help spixfer", "help syslock", "help flashinfo",
            "help flashwp", "help rw", "help typec", "help pd", "help tcpc",
            "help hcdebug", "help hash"]:
    print(f"=== {cmd} ===")
    print(ec_cmd(cmd, wait=0.6))

print()
print("=== flashinfo ===")
print(ec_cmd("flashinfo", wait=1.0))
print("=== flashwp ===")
print(ec_cmd("flashwp", wait=1.0))
print("=== syslock ===")
print(ec_cmd("syslock", wait=1.0))
print("=== sysinfo ===")
print(ec_cmd("sysinfo", wait=1.0))
print("=== pd 0 state ===")
print(ec_cmd("pd 0 state", wait=1.0))

print()
print("=== flashrom -V (verbose) ===")
r = subprocess.run(["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
                    "-c", "W25Q64BV/W25Q64CV/W25Q64FV", "--flash-name", "-V"],
                   capture_output=True, text=True, timeout=20)
print(f"exit={r.returncode}")
for ln in (r.stdout + r.stderr).splitlines()[:50]:
    print(f"  | {ln}")

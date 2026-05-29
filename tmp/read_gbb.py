#!/usr/bin/env python3
"""Same atomic pattern as flash_rw.py — works because of timing alignment."""
import subprocess, time, serial
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/usr/sbin/flashrom"
CHIP = "W25Q64BV/W25Q64CV/W25Q64FV"
def ec(cmd, wait=1.2):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
    s.dtr = False; s.rts = False; s.open()
    s.write((cmd + "\r").encode()); s.flush(); time.sleep(wait)
    r = s.read(8192); s.close(); return r.decode("latin1","replace")

print("[1] AP off:", ec("gale power off").strip()[-40:])
print("[2] flashrom -r --fmap -i GBB")
r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-c", CHIP,
                    "-r", "tmp/gbb_only.bin", "--fmap", "-i", "GBB"],
                   capture_output=True, text=True, timeout=120)
for ln in (r.stdout + r.stderr).splitlines()[-6:]:
    print("   |", ln)
print("rc:", r.returncode)

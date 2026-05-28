#!/usr/bin/env python3
"""Atomic RW flash: reboot to a STABLE dev-mode boot (no crash), then
power-off immediately followed by flashrom with NO intervening delay
(the flash rail decays fast after gale power off)."""
import os, time, serial, sys

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/usr/sbin/flashrom"
IMG = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-netboot-rw.bin"
REGION = sys.argv[1] if len(sys.argv) > 1 else "FW_MAIN_A"

def ec(cmd, wait=0.6):
    try:
        s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
        s.dtr = False; s.rts = False; s.open()
        s.write((cmd + "\r").encode()); s.flush(); time.sleep(wait); s.read(4096); s.close()
    except Exception:
        pass

print("[reboot -> stable dev-mode boot]")
ec("reboot")
time.sleep(16)                       # AP boots to stable dev screen (no crash)
print("[ATOMIC: gale power off, then flashrom immediately]")
ec("gale power off", 0.4)            # minimal settle; rail still powered
rc = os.system(f"sudo {FR} -p raiden_debug_spi -w {IMG} --fmap -i {REGION} "
               f"2>&1 | grep -iE 'Found|Erasing|Writing|Verifying|VERIFIED|FAILED|done'")
print("flashrom rc:", rc)

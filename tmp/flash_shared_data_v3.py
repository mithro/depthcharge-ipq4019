#!/usr/bin/env python3
"""Aggressive reset before flash: uhubctl power-cycle gale, wait for
SuzyQ to re-enumerate, EC reboot to clear SPI bridge state, then
gale power off and flashrom.
"""
import subprocess, time, os, sys, serial

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
IMG = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-shared-data-v22.bin"


def ec_send(cmd, wait=1.0, read=True):
    try:
        s = serial.Serial(EC, 115200, timeout=0.2)
        s.write(b"\r"); time.sleep(0.2)
        try: s.read(8192)
        except Exception: pass
        s.write((cmd + "\r").encode()); time.sleep(wait)
        if read:
            try:
                print(s.read(4096).decode("latin1", "replace").rstrip(), flush=True)
            except Exception as e:
                print(f"  (read err: {e})", flush=True)
        s.close()
    except Exception as e:
        print(f"  EC open err (ignored): {e}", flush=True)


def wait_for_ec():
    for _ in range(120):
        if os.path.exists(EC):
            return True
        time.sleep(0.5)
    return False


print("=== uhubctl power-cycle gale (hub 1-1 port 3) ===")
subprocess.run(["sudo", "uhubctl", "-l", "1-1", "-p", "3", "-a", "cycle"],
               check=True)
time.sleep(4)
if not wait_for_ec():
    sys.exit("EC tty never came back")
time.sleep(3)

print("=== EC reboot to clear SPI bridge state ===")
ec_send("reboot", wait=5, read=False)
time.sleep(6)
if not wait_for_ec():
    sys.exit("EC tty never came back after reboot")
time.sleep(2)

print("=== gale power off ===")
ec_send("gale power off", wait=2)
time.sleep(2)

print("=== flashrom write SHARED_DATA ===")
r = subprocess.run(
    ["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
     "--fmap", "-w", IMG, "-i", "SHARED_DATA"],
    capture_output=True, text=True, timeout=180)
for ln in (r.stdout + r.stderr).splitlines()[-30:]:
    print(f"  | {ln}")
print(f"exit: {r.returncode}")
sys.exit(r.returncode)

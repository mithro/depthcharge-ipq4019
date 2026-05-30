#!/usr/bin/env python3
"""Aggressive recovery sequence then restore stock vboot depthcharge."""
import subprocess, time, sys, os, serial

STOCK = "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"


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


def wait_for_ec(timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(EC):
            return True
        time.sleep(0.5)
    return False


print("=== uhubctl power-cycle gale ===")
subprocess.run(["sudo", "uhubctl", "-l", "1-1", "-p", "3", "-a", "cycle"], check=True)
time.sleep(5)
if not wait_for_ec():
    sys.exit("EC tty did not return after uhubctl cycle")
time.sleep(3)

print("=== EC reboot ===")
ec_send("reboot", wait=4, read=False)
time.sleep(6)
if not wait_for_ec():
    sys.exit("EC tty did not return after reboot")
time.sleep(3)

print("=== gale power off ===")
ec_send("gale power off", 2)
time.sleep(3)

print("=== flashrom -w stock --image VBLOCK_A,B + FW_MAIN_A,B (NO RW_FWID this time) ===")
r = subprocess.run(
    ["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
     "--fmap", "-w", STOCK,
     "-i", "VBLOCK_A", "-i", "VBLOCK_B",
     "-i", "FW_MAIN_A", "-i", "FW_MAIN_B"],
    capture_output=True, text=True, timeout=300)
for ln in (r.stdout + r.stderr).splitlines()[-30:]:
    print(f"  | {ln}")
print(f"exit: {r.returncode}")

if r.returncode != 0:
    sys.exit(r.returncode)

print()
print("=== gale dev off, rec off, power on ===")
ec_send("gale dev off", 1)
ec_send("gale rec off", 1)
ec_send("gale power on", 2)
print()
print("OK — should now boot from eMMC")

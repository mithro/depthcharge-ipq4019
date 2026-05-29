#!/usr/bin/env python3
"""Test: EC reboot hard followed by `gale power on`/off sequence from
flash_rw.py. The flash_rw.py procedure may need a fully booted AP first
so that the EC's power-down sequence reaches the right idle state."""
import subprocess, time, serial, os

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"

def ec_cmd(cmd, wait=0.8):
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

def flashrom_probe(label):
    r = subprocess.run(["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
                        "-c", "W25Q64BV/W25Q64CV/W25Q64FV", "--flash-name"],
                       capture_output=True, text=True, timeout=15)
    found = r.returncode == 0
    print(f"  flashrom @ [{label}]: exit={r.returncode} found={found}")
    for ln in (r.stdout + r.stderr).splitlines():
        if "EEPROM" in ln or "Winbond" in ln or "Found" in ln or "RDID" in ln:
            print(f"    | {ln}")
    return found

# Step 1: Hard cycle to start from clean state
print("[Step 1] UCSI hard cycle")
subprocess.run(["sudo", "sh", "-c",
    "echo 0x10003 > /sys/kernel/debug/usb/ucsi/USBC000:00/command"], check=True)
time.sleep(0.3)
while subprocess.run(["lsusb", "-d", "18d1:500f"],
                     capture_output=True, text=True).stdout:
    time.sleep(0.1)
for i in range(100):
    if subprocess.run(["lsusb", "-d", "18d1:500f"],
                      capture_output=True, text=True).stdout:
        break
    time.sleep(0.1)
for i in range(60):
    if os.path.exists(EC): break
    time.sleep(0.1)
time.sleep(2.0)
print(f"  EC alive: {ec_cmd('version', wait=0.5)[:80]}")

print()
print("[Step 2] Probe AP after `gale power on` (let AP boot)")
print(ec_cmd("gale power on", wait=1.5))
print("  Waiting 8s for AP to boot (probably crashes/halts)...")
time.sleep(8)
print("  State now:")
for gp in ["VDD_1P1_CPU_EN", "VDD_3P3_EN", "VDD_1P8_EN", "SYS_PWR_EN"]:
    out = ec_cmd(f"gpioget {gp}", wait=0.4)
    for ln in out.splitlines():
        if gp in ln and "gpioget" not in ln:
            print(f"    {ln.strip()}")

print()
print("[Step 3] flash_rw.py procedure: `gale power off` then flashrom IMMEDIATELY")
print(ec_cmd("gale power off", wait=1.2))
flashrom_probe("post `gale power off`")

print()
print("[Step 4] Check state after attempt")
for gp in ["VDD_1P1_CPU_EN", "VDD_3P3_EN", "VDD_1P8_EN", "SYS_PWR_EN"]:
    out = ec_cmd(f"gpioget {gp}", wait=0.4)
    for ln in out.splitlines():
        if gp in ln and "gpioget" not in ln:
            print(f"    {ln.strip()}")

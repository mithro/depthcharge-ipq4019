#!/usr/bin/env python3
"""Same as state_probe3 but waits longer for full EC enumeration and
dumps raw EC responses without parsing."""
import subprocess, time, serial, os

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"

def ec_cmd(cmd, wait=1.0):
    s = serial.Serial()
    s.port = EC; s.baudrate = 115200; s.timeout = 0.2
    s.dtr = False; s.rts = False
    s.open()
    s.write(b"\r"); time.sleep(0.2); s.read(8192)
    s.write((cmd + "\r").encode()); s.flush()
    time.sleep(wait)
    out = s.read(16384).decode("latin1", "replace")
    s.close()
    return out

print("[Step 1] UCSI CONNECTOR_RESET")
subprocess.run(["sudo", "sh", "-c",
    "echo 0x10003 > /sys/kernel/debug/usb/ucsi/USBC000:00/command"], check=True)
# Wait for hub branch to disappear AND reappear
time.sleep(0.3)
while subprocess.run(["lsusb", "-d", "18d1:500f"],
                     capture_output=True, text=True).stdout:
    time.sleep(0.1)
print("  gale disappeared")
for i in range(100):
    if subprocess.run(["lsusb", "-d", "18d1:500f"],
                      capture_output=True, text=True).stdout:
        print(f"  gale reappeared at {i*0.1:.1f}s")
        break
    time.sleep(0.1)
for i in range(60):
    if os.path.exists(EC): break
    time.sleep(0.1)
time.sleep(2.0)  # let EC firmware fully init

print()
print("[Step 2] Sanity ping (version)")
print(ec_cmd("version"))

print("[Step 3] DEFAULT GPIO state (raw responses)")
for gp in ["VDD_1P1_CPU_EN", "VDD_3P3_EN", "VDD_3P3_2G_EN",
          "VDD_1P35_EN", "VDD_1P8_EN", "SYS_PWR_EN", "WP_L"]:
    print(f"--- gpioget {gp} ---")
    print(ec_cmd(f"gpioget {gp}"))

print()
print("[Step 4] flashrom --flash-name (AP NEVER booted)")
r = subprocess.run(["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
                    "-c", "W25Q64BV/W25Q64CV/W25Q64FV", "--flash-name"],
                   capture_output=True, text=True, timeout=20)
print(f"exit={r.returncode}")
for ln in (r.stdout + r.stderr).splitlines():
    print("  |", ln)

#!/usr/bin/env python3
"""UCSI hard cycle, never `gale power on`. Test what state EC defaults to,
and whether flashrom works without ever booting the AP."""
import subprocess, time, serial, os

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"

def ec_cmd(cmd, wait=0.8):
    s = serial.Serial()
    s.port = EC; s.baudrate = 115200; s.timeout = 0.2
    s.dtr = False; s.rts = False
    s.open()
    s.write(b"\r"); time.sleep(0.1); s.read(8192)
    s.write((cmd + "\r").encode()); s.flush()
    time.sleep(wait)
    out = s.read(16384).decode("latin1", "replace")
    s.close()
    return out

print("=" * 60)
print("Step 1: UCSI CONNECTOR_RESET (drop ALL power to gale)")
print("=" * 60)
subprocess.run(["sudo", "sh", "-c",
    "echo 0x10003 > /sys/kernel/debug/usb/ucsi/USBC000:00/command"], check=True)

# Wait for re-enumeration
print("Waiting for re-enumeration...")
for i in range(60):
    out = subprocess.run(["lsusb"], capture_output=True, text=True).stdout
    if "18d1:500f" in out:
        print(f"  EC re-appeared after {i*0.1:.1f}s")
        break
    time.sleep(0.1)
else:
    print("  EC did NOT re-appear in 6s")
    raise SystemExit(1)

# Wait for serial node
for i in range(60):
    if os.path.exists(EC): break
    time.sleep(0.1)
time.sleep(1.0)  # let EC settle

print()
print("=" * 60)
print("Step 2: DEFAULT GPIO state after UCSI cycle (no commands sent)")
print("=" * 60)
for gp in ["VDD_1P1_CPU_EN", "VDD_3P3_EN", "VDD_3P3_2G_EN",
          "VDD_1P35_EN", "VDD_1P8_EN", "SYS_PWR_EN", "WP_L",
          "ENTERING_REC", "ENTERING_DEV"]:
    out = ec_cmd(f"gpioget {gp}").strip().split("\n")
    for ln in out:
        if gp in ln:
            print(f"  {ln.strip()}")
            break

print()
print("=" * 60)
print("Step 3: flashrom --flash-name (AP NEVER booted)")
print("=" * 60)
r = subprocess.run(["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
                    "-c", "W25Q64BV/W25Q64CV/W25Q64FV", "--flash-name"],
                   capture_output=True, text=True, timeout=20)
print(f"exit={r.returncode}")
for ln in (r.stdout + r.stderr).splitlines():
    print("  |", ln)

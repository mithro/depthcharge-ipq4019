#!/usr/bin/env python3
"""From the all-off post-UCSI state, set VDD_3P3_EN=1 (and possibly other
rails), then try flashrom. Test multiple rail combinations."""
import subprocess, time, serial

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

def flashrom_probe(label):
    r = subprocess.run(["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
                        "-c", "W25Q64BV/W25Q64CV/W25Q64FV", "--flash-name"],
                       capture_output=True, text=True, timeout=20)
    found = "Winbond" in (r.stdout + r.stderr) or r.returncode == 0
    print(f"  flashrom @ [{label}]: exit={r.returncode} found={found}")
    for ln in (r.stdout + r.stderr).splitlines():
        if "EEPROM" in ln or "Winbond" in ln or "Found" in ln:
            print(f"    | {ln}")

print("Confirm post-UCSI starting state:")
for gp in ["VDD_1P1_CPU_EN", "VDD_3P3_EN", "VDD_1P8_EN", "SYS_PWR_EN"]:
    out = ec_cmd(f"gpioget {gp}")
    for ln in out.splitlines():
        if gp in ln and "gpioget" not in ln:
            print(f"  {ln.strip()}")

print()
print("--- Test A: only VDD_3P3_EN=1, CPU rail stays 0 ---")
ec_cmd("gpioset VDD_3P3_EN 1")
time.sleep(0.5)
flashrom_probe("A: 3P3 on, CPU off")

print()
print("--- Test B: also VDD_1P8_EN=1 ---")
ec_cmd("gpioset VDD_1P8_EN 1")
time.sleep(0.5)
flashrom_probe("B: 3P3 on, 1P8 on, CPU off")

print()
print("--- Test C: also VDD_1P35_EN=1 (DDR rail, but maybe matters) ---")
ec_cmd("gpioset VDD_1P35_EN 1")
time.sleep(0.5)
flashrom_probe("C: 3P3 + 1P8 + 1P35, CPU off")

print()
print("--- Test D: full bringup via `gale power on`, then CPU off via gpioset ---")
ec_cmd("gale power on", wait=2.0)
print("  Wait 5s for boot to be in progress...")
time.sleep(5)
ec_cmd("gpioset VDD_1P1_CPU_EN 0", wait=0.5)
time.sleep(0.5)
for gp in ["VDD_1P1_CPU_EN", "VDD_3P3_EN", "VDD_1P8_EN", "SYS_PWR_EN"]:
    out = ec_cmd(f"gpioget {gp}")
    for ln in out.splitlines():
        if gp in ln and "gpioget" not in ln:
            print(f"  {ln.strip()}")
flashrom_probe("D: full rails, CPU just forced off")

print()
print("--- Test E: hammer CPU off + flashrom in tight loop ---")
for attempt in range(3):
    ec_cmd("gpioset VDD_1P1_CPU_EN 0", wait=0.2)
    flashrom_probe(f"E.{attempt}")

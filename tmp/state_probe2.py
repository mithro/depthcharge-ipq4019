#!/usr/bin/env python3
"""Test theory: AP-CPU-off + flash-rail-on = flashrom works.
Procedure under test: gpioset VDD_3P3_EN 1; flashrom.
(Do NOT issue `gale power off` — it cuts the flash rail.)
"""
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

print("State check before:")
print("  ", ec_cmd("gpioget VDD_1P1_CPU_EN").strip().split("\n")[1])
print("  ", ec_cmd("gpioget VDD_3P3_EN").strip().split("\n")[1])
print("  ", ec_cmd("gpioget SYS_PWR_EN").strip().split("\n")[1])

print()
print("Step A: re-enable VDD_3P3_EN explicitly (flash power on)")
print(ec_cmd("gpioset VDD_3P3_EN 1"))
print("  After:", ec_cmd("gpioget VDD_3P3_EN").strip().split("\n")[1])

print()
print("Step B: confirm AP CPU still off")
print("  ", ec_cmd("gpioget VDD_1P1_CPU_EN").strip().split("\n")[1])

print()
print("Step C: flashrom --flash-name")
time.sleep(0.5)
r = subprocess.run(["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
                    "-c", "W25Q64BV/W25Q64CV/W25Q64FV", "--flash-name"],
                   capture_output=True, text=True, timeout=20)
print(f"exit={r.returncode}")
for ln in (r.stdout + r.stderr).splitlines():
    print("  |", ln)

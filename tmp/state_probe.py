#!/usr/bin/env python3
"""Probe device state honestly. No assumptions.

Q1: What does EC report about AP power state right now?
Q2: After `gale power off`, what's VDD_1P1_CPU_EN?
Q3: Does flashrom --flash-name work right now?
"""
import subprocess, time, serial

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"

def ec_cmd(cmd, wait=0.8):
    s = serial.Serial()
    s.port = EC; s.baudrate = 115200; s.timeout = 0.2
    s.dtr = False; s.rts = False
    s.open()
    s.write(b"\r")  # wake up
    time.sleep(0.1)
    s.read(8192)    # drain
    s.write((cmd + "\r").encode())
    s.flush()
    time.sleep(wait)
    out = s.read(16384).decode("latin1", "replace")
    s.close()
    return out

print("=" * 60)
print("Q0: EC ID/version (sanity)")
print("=" * 60)
print(ec_cmd("version"))

print("=" * 60)
print("Q1a: CURRENT GPIO state — VDD_1P1_CPU_EN")
print("=" * 60)
print(ec_cmd("gpioget VDD_1P1_CPU_EN"))

print("=" * 60)
print("Q1b: CURRENT GPIO state — VDD_3P3_EN (flash power)")
print("=" * 60)
print(ec_cmd("gpioget VDD_3P3_EN"))

print("=" * 60)
print("Q1c: CURRENT GPIO state — SYS_PWR_EN")
print("=" * 60)
print(ec_cmd("gpioget SYS_PWR_EN"))

print("=" * 60)
print("Q1d: CURRENT GPIO state — WP_L")
print("=" * 60)
print(ec_cmd("gpioget WP_L"))

print("=" * 60)
print("Q2: Issue `gale power off`, then check VDD_1P1_CPU_EN")
print("=" * 60)
print(ec_cmd("gale power off"))
print("--- post `gale power off`: VDD_1P1_CPU_EN")
print(ec_cmd("gpioget VDD_1P1_CPU_EN"))
print("--- post `gale power off`: VDD_3P3_EN")
print(ec_cmd("gpioget VDD_3P3_EN"))

print("=" * 60)
print("Q3: flashrom --flash-name NOW (no extra setup)")
print("=" * 60)
r = subprocess.run(["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
                    "-c", "W25Q64BV/W25Q64CV/W25Q64FV", "--flash-name"],
                   capture_output=True, text=True, timeout=20)
print(f"exit={r.returncode}")
print("--- stdout ---")
print(r.stdout)
print("--- stderr ---")
print(r.stderr)

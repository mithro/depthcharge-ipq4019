#!/usr/bin/env python3
"""Capture FULL AP UART output across a gale boot to see what happens
after `Please press Enter to activate this console.` — including any
ath10k_pci panic, kernel logs, or modprobe events.

Assumes dnsmasq is already running on the desired Pi NIC.

Writes captured bytes verbatim to tmp/ap-uart-<timestamp>.log so we
can grep for warnings, error messages, panics, register dumps.
"""
import os, sys, time, threading, subprocess, datetime
import serial

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"
CAPTURE_S = int(sys.argv[1]) if len(sys.argv) > 1 else 180
LOG_BASE = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp"

def sh(cmd):
    print(f"  $ {cmd}", flush=True)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout.strip(): print(f"    {r.stdout.strip()[:300]}", flush=True)
    if r.stderr.strip(): print(f"    err: {r.stderr.strip()[:300]}", flush=True)
    return r

def ec_open():
    return serial.Serial(EC, 115200, timeout=0.2)

def ec_cmd(ec, cmd, wait=0.5):
    ec.write(b"\r"); time.sleep(0.15); ec.read(8192)
    ec.write((cmd + "\r").encode()); time.sleep(wait)
    return ec.read(16384).decode("latin1", "replace")

stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
logpath = f"{LOG_BASE}/ap-uart-{stamp}.log"
print(f"=== Will write AP UART to: {logpath}")

print("=== uhubctl cycle gale (hub 1-1 port 3) ===")
sh("sudo uhubctl -l 1-1 -p 3 -a cycle")
time.sleep(3)
for _ in range(60):
    if os.path.exists(EC) and os.path.exists(AP):
        break
    time.sleep(0.5)
else:
    sys.exit("SuzyQ ttys did not come back")
time.sleep(2)

print()
print("=== EC reboot to clear stuck dev/rec state ===")
try:
    ec = ec_open(); ec.write(b"\rreboot\r"); ec.close()
except Exception as e:
    print(f"  ec reboot send err (ignored): {e}")
time.sleep(5)
for _ in range(60):
    if os.path.exists(EC) and os.path.exists(AP):
        break
    time.sleep(0.5)
time.sleep(2)

print()
print("=== EC: gale dev off, rec off, power on ===")
ec = ec_open()
print(ec_cmd(ec, "gale dev off"))
print(ec_cmd(ec, "gale rec off"))
print(ec_cmd(ec, "gale power on", 1.5))
ec.close()

print()
print(f"=== capture AP UART {CAPTURE_S}s ===", flush=True)
fp = open(logpath, "wb")
stop = False
def reader():
    while not stop:
        try:
            s = serial.Serial(AP, 115200, timeout=0.1)
            while not stop:
                d = s.read(8192)
                if d:
                    fp.write(d)
                    fp.flush()
            s.close()
        except Exception:
            time.sleep(0.3)
threading.Thread(target=reader, daemon=True).start()

t0 = time.time()
last_print = 0
while time.time() - t0 < CAPTURE_S:
    time.sleep(2)
    el = int(time.time() - t0)
    if el - last_print >= 20:
        last_print = el
        sz = os.path.getsize(logpath) if os.path.exists(logpath) else 0
        print(f"  t={el}s  log={sz}B", flush=True)

stop = True; time.sleep(0.5); fp.close()
print(f"=== wrote {os.path.getsize(logpath)} bytes to {logpath}")
print()
print("=== last 80 lines ===")
with open(logpath, "rb") as f:
    data = f.read().decode("latin1", "replace")
for line in data.splitlines()[-80:]:
    print(f"| {line[:240]}")

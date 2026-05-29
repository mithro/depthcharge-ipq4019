#!/usr/bin/env python3
"""Boot gale on rpi4 with predetermined Pi NIC state — don't touch
NIC config, just verify which gale PHY links.

Assumes dnsmasq is already running on the desired Pi NIC.
"""
import subprocess, sys, time, os, threading, serial

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"
CAPTURE_S = 75

def sh(cmd, check=True):
    print(f"  $ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout.strip(): print(f"    {r.stdout.strip()[:200]}")
    if r.stderr.strip(): print(f"    err: {r.stderr.strip()[:200]}")
    if check and r.returncode != 0:
        sys.exit(f"FAILED: {cmd}")
    return r

def ec_open():
    return serial.Serial(EC, 115200, timeout=0.2)

def ec_cmd(ec, cmd, wait=0.5):
    ec.write(b"\r"); time.sleep(0.15); ec.read(8192)
    ec.write((cmd + "\r").encode()); time.sleep(wait)
    return ec.read(16384).decode("latin1", "replace")

# Power-cycle gale (uhubctl 1-1 p3)
print("=== uhubctl power-cycle gale ===")
sh("sudo uhubctl -l 1-1 -p 3 -a cycle")
time.sleep(3)
for _ in range(60):
    if os.path.exists(EC) and os.path.exists(AP):
        break
    time.sleep(0.5)
time.sleep(2)

# EC reboot to clear stuck dev/rec state
print()
print("=== EC reboot ===")
try:
    ec = ec_open(); ec.write(b"\rreboot\r"); ec.close()
except Exception as e:
    print(f"  ec reboot err: {e}")
time.sleep(5)
for _ in range(60):
    if os.path.exists(EC) and os.path.exists(AP):
        break
    time.sleep(0.5)
time.sleep(2)

# gale power on
print()
print("=== gale power on ===")
ec = ec_open()
print(ec_cmd(ec, "gale dev off"))
print(ec_cmd(ec, "gale rec off"))
print(ec_cmd(ec, "gale power on", 1.5))
ec.close()

# Capture AP UART
print()
print(f"=== capture AP UART {CAPTURE_S}s ===")
ap_buf = []; stop = False
def reader():
    while not stop:
        try:
            s = serial.Serial(AP, 115200, timeout=0.1)
            while not stop:
                d = s.read(8192)
                if d: ap_buf.append(d)
            s.close()
        except Exception:
            time.sleep(0.3)
threading.Thread(target=reader, daemon=True).start()

t0 = time.time()
while time.time() - t0 < CAPTURE_S:
    txt = b"".join(ap_buf).decode("latin1", "replace")
    if "Link is Up - 1Gbps/Full" in txt and "qca8k" in txt:
        time.sleep(10); break
    if "panic" in txt or "Data Abort" in txt:
        time.sleep(3); break
    time.sleep(0.5)
stop = True; time.sleep(0.5)

text = b"".join(ap_buf).decode("latin1", "replace")
lines = [l for l in text.splitlines() if l.strip()]
print(f"\n=== {len(lines)} AP UART lines ===")
print()
print("=== KEY EVENTS ===")
for l in lines:
    if any(k in l for k in (
        "ipq4019: PHY ", "ipq4019: link up",
        "Sending DHCP", "Waiting for reply... done",
        "bytes long", "Loading FIT", "Image kernel", "Image fdt",
        "Compat preference", "Choosing best", "Exiting depthcharge",
        "qca8k-ipq4019", "PSGMII calibration",
        "Link is Up", "Link is Down",
        "panic", "Data Abort")):
        print(f"  | {l[:200]}")

#!/usr/bin/env python3
"""Pi-side gale TFTP boot test.

For each test:
- Bring ONE Pi USB-eth NIC up, OTHER NIC fully down (so gale only sees
  one of its two RJ45 jacks as having a link partner).
- Start dnsmasq bound to the active NIC.
- Power-cycle gale via uhubctl, then explicitly `gale power on` via EC.
- Capture AP UART for 90 s, report which gale PHY linked (3 = LAN jack,
  4 = WAN jack per the kernel's qca8k port mapping).

Usage: python3 pi_boot_test.py <active_nic>
       e.g. eth-gwan or eth-glan (NIC NAMES ARE NOT TRUSTED — the test
       reports what gale actually sees).
"""
import subprocess, sys, time, os, threading

if len(sys.argv) != 2:
    sys.exit(f"usage: {sys.argv[0]} <active_nic>")

ACTIVE = sys.argv[1]
OTHER  = "eth-glan" if ACTIVE == "eth-gwan" else "eth-gwan"
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"
CAPTURE_S = 90

def sh(cmd, check=True):
    print(f"  $ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout.strip(): print(f"    {r.stdout.strip()[:200]}")
    if r.stderr.strip(): print(f"    err: {r.stderr.strip()[:200]}")
    if check and r.returncode != 0:
        sys.exit(f"FAILED: {cmd}")
    return r

import serial

def ec_open():
    return serial.Serial(EC, 115200, timeout=0.2)

def ec_cmd(ec, cmd, wait=0.5):
    ec.write(b"\r"); time.sleep(0.15); ec.read(8192)
    ec.write((cmd + "\r").encode()); time.sleep(wait)
    return ec.read(16384).decode("latin1", "replace")

# 1. Tear down anything from previous run
sh("sudo pkill -9 -f 'dnsmasq.*dnsmasq-gwifi' || true", check=False)
sh(f"sudo ip addr flush dev {ACTIVE} 2>/dev/null || true", check=False)
sh(f"sudo ip addr flush dev {OTHER} 2>/dev/null || true", check=False)
sh("sudo rm -f /tmp/dnsmasq-gwifi.log /tmp/dnsmasq-gwifi.leases", check=False)
time.sleep(1)

# 2. Bring the OTHER NIC fully DOWN so gale can't link through it
sh(f"sudo ip link set {OTHER} down")
sh(f"sudo ip link set {ACTIVE} up")
sh(f"sudo ip addr add 10.42.1.1/24 dev {ACTIVE}")
time.sleep(2)

# 3. Render dnsmasq config with the actual interface name and launch
sh(f"sed 's/^interface=IFACE/interface={ACTIVE}/' /tmp/dnsmasq-gwifi.conf "
   f"| sudo tee /tmp/dnsmasq-gwifi.active.conf > /dev/null")
sh("sudo dnsmasq --conf-file=/tmp/dnsmasq-gwifi.active.conf")
time.sleep(1)

# 4. Power-cycle gale + reboot EC to clear stuck state, then gale power on
print()
print("=== uhubctl power cycle gale ===")
sh("sudo uhubctl -l 1-1 -p 3 -a cycle")
time.sleep(3)
for _ in range(60):
    if os.path.exists(EC) and os.path.exists(AP):
        break
    time.sleep(0.5)
else:
    sys.exit("SuzyQ tty did not return")
time.sleep(2)

# Reboot the EC to ensure dev/rec switches are reset to OFF
print()
print("=== EC reboot to clear dev/rec state ===")
try:
    ec = ec_open()
    ec.write(b"\rreboot\r")
    ec.close()
except Exception as e:
    print(f"  ec reboot send err (ignored): {e}")
time.sleep(5)
for _ in range(60):
    if os.path.exists(EC) and os.path.exists(AP):
        break
    time.sleep(0.5)
time.sleep(2)

# 5. gale power on via EC
print()
print("=== EC: gale dev off, rec off, power on ===")
ec = ec_open()
print(ec_cmd(ec, "gale dev off"))
print(ec_cmd(ec, "gale rec off"))
print(ec_cmd(ec, "gale", 0.5))
print(ec_cmd(ec, "gale power on", 1.5))
ec.close()

# 6. Open AP UART reader BEFORE first boot output appears
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
    if "Link is Up - 1Gbps/Full" in txt or "Link is Up - 100Mbps/Full" in txt:
        # Kernel saw its link — boot reached running kernel.
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

print()
print("=== dnsmasq summary ===")
sh("sudo grep -E 'DHCP(REQUEST|ACK|DISCOVER|OFFER)|TFTP|failed' /tmp/dnsmasq-gwifi.log | head -20",
   check=False)

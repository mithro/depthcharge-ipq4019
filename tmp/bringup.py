#!/usr/bin/env python3
"""Driver bring-up: UCSI cycle, power on, capture all the way through (or
to first crash/hang). Detailed gate tracking + early-exit on `Data Abort`."""
import subprocess, time, os, serial, threading, sys

EC  = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP  = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"

def lsusb_has(vp):
    return vp in subprocess.run(["lsusb"], capture_output=True, text=True).stdout
def ec(c, w=0.4):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.15
    s.dtr = False; s.rts = False; s.open()
    s.write((c + "\r").encode()); s.flush(); time.sleep(w); s.read(8192); s.close()

# Gates we want to see, in order, with their needles:
GATES = [
    ("bootblock",           "bootblock start"),
    ("FMAP/GBB found",      "GBB found"),
    ("VBLOCK verified",     "Verifying preamble"),
    ("body OK (no recov)",  "VbBootDeveloper"),
    ("(neg) recovery",      "VbBootRecovery"),
    ("(neg) body hash fail","Digest check failed"),
    ("Starting netboot",    "Starting netboot on gale"),
    ("driver: MAC",         "ipq4019: MAC"),
    ("driver: mdio_init",   "mdio_init"),
    ("PSGMII self-test",    "PSGMII self-test"),
    ("PSGMII passed",       "self-test passed"),
    ("(neg) PSGMII fail",   "calibration failed"),
    ("switch init",         "ipq4019: switch"),
    ("edma init",           "ipq4019: edma"),
    ("net_add_device",      "net_add_device"),
    ("Waiting for link",    "Waiting for"),
    ("DHCPDISCOVER",        "DHCPDISCOVER"),
    ("DHCPACK",             "DHCPACK"),
    ("TFTP openwrt",        "openwrt-gale.itb"),
    ("Starting kernel",     "Starting kernel"),
    ("Linux booting",       "Linux version"),
    ("CRASH!",              "Data Abort"),
]

# UCSI cycle (this drops the ethernet adapter — IP must be re-added after)
print("[UCSI CONNECTOR_RESET]")
subprocess.run(["sudo", "sh", "-c",
    "echo 0x10003 > /sys/kernel/debug/usb/ucsi/USBC000:00/command"], check=True)
for _ in range(40):
    if lsusb_has("18d1:500f"): break
    time.sleep(0.05)
for _ in range(30):
    if os.path.exists(EC): break
    time.sleep(0.1)
# Wait extra for ethernet adapter to re-enumerate as well
time.sleep(2.0)

# Re-add the netboot server's IP — UCSI cycle dropped the interface, and
# NetworkManager wipes the address when the adapter re-enumerates. dnsmasq
# is already running, but it needs the iface to have an IP to send DHCP
# responses.
print("[restore 10.42.1.1/24 on enx00e04c68016b after UCSI cycle]")
subprocess.run(["sudo","ip","addr","add","10.42.1.1/24","dev","enx00e04c68016b"],
               capture_output=True, text=True)
subprocess.run(["sudo","ip","link","set","enx00e04c68016b","up"], capture_output=True, text=True)
# Verify
r = subprocess.run(["ip","addr","show","enx00e04c68016b"], capture_output=True, text=True)
for ln in r.stdout.splitlines():
    if "inet " in ln:
        print(f"  {ln.strip()}")
# Restart dnsmasq so it sees the address
print("[restart dnsmasq with current iface state]")
subprocess.run(["uv","run","--no-project","python","tmp/netboot_server.py","start","openwrt-gale.itb"],
               capture_output=True, text=True, timeout=20)
time.sleep(1)

# Don't set dev/rec — GBB FORCE_DEV_SWITCH_ON does the work
print("[gale dev off, rec off, power on  (GBB FORCE_DEV will handle dev mode)]")
ec("gale dev off"); ec("gale rec off")

# Start AP UART reader BEFORE power-on so we don't miss bootblock
ap_buf = []; stop = False; seen_gates = set()
def reader():
    while not stop:
        try:
            s = serial.Serial(); s.port = AP; s.baudrate = 115200; s.timeout = 0.05
            s.dtr = False; s.rts = False; s.open()
            while not stop:
                d = s.read(4096)
                if d: ap_buf.append(d)
            s.close()
        except Exception:
            time.sleep(0.2)
threading.Thread(target=reader, daemon=True).start()
time.sleep(0.3)

ec("gale power on", w=0.4)
print("[booting; gate tracking with early exit on crash]")

# Track gates as they appear, watching for crash
t0 = time.time()
last_report = 0
crashed = False
while time.time() - t0 < 90:
    time.sleep(0.5)
    text = b"".join(ap_buf).decode("latin1", "replace")
    for label, needle in GATES:
        if label not in seen_gates and needle in text:
            elapsed = time.time() - t0
            seen_gates.add(label)
            print(f"  t+{elapsed:5.1f}s  [{label}]")
            if label == "CRASH!":
                crashed = True
    if crashed:
        print("  *** CRASH detected — stopping capture early ***")
        break
    # Periodic reachable-gate count
    if time.time() - last_report > 15:
        last_report = time.time()
        positive_gates = [g for g in seen_gates if not g.startswith("(neg)") and g != "CRASH!"]
        neg_gates = [g for g in seen_gates if g.startswith("(neg)")]
        print(f"  ... t+{time.time()-t0:.0f}s: {len(positive_gates)} positive gates, {len(neg_gates)} negative")

stop = True
time.sleep(0.5)

text = b"".join(ap_buf).decode("latin1", "replace")
lines = [l for l in text.splitlines() if l.strip()]
print()
print(f"=== TOTAL: {len(lines)} AP UART lines captured ===")
print()
print("=== GATES ===")
for label, needle in GATES:
    print(f"  [{'X' if label in seen_gates else ' '}] {label}")
print()
print("=== LAST 25 lines ===")
for l in lines[-25:]:
    print("  >", l[:160])

# Also show dnsmasq activity
print()
print("=== dnsmasq log (last 20 lines) ===")
log = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/dnsmasq-netboot.log"
if os.path.exists(log):
    r = subprocess.run(["sudo", "tail", "-20", log], capture_output=True, text=True)
    for l in r.stdout.splitlines():
        print("  |", l[:170])

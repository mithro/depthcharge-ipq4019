#!/usr/bin/env python3
"""T-A through T-F: boot v3 and verify basic operation + halt-fallback + SuzyQ access."""
import subprocess, time, os, serial, threading

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"

def lsusb_has(vp):
    return vp in subprocess.run(["lsusb"], capture_output=True, text=True).stdout

def ec(c, w=0.4):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.15
    s.dtr = False; s.rts = False; s.open()
    s.write((c + "\r").encode()); s.flush(); time.sleep(w); s.read(8192); s.close()

# Restart netboot server with correct IP (UCSI cycle will drop iface)
print("[setup: clean dnsmasq + AP UART reader]")
subprocess.run(["uv","run","--no-project","python","tmp/netboot_server.py","stop"],
               capture_output=True, timeout=15)

# UCSI cycle
print("\n[UCSI CONNECTOR_RESET]")
subprocess.run(["sudo","sh","-c",
    "echo 0x10003 > /sys/kernel/debug/usb/ucsi/USBC000:00/command"], check=True)
for _ in range(40):
    if lsusb_has("18d1:500f"): break
    time.sleep(0.05)
for _ in range(30):
    if os.path.exists(EC): break
    time.sleep(0.1)
time.sleep(2)  # let ethernet adapter re-enumerate

# Re-add netboot IP after UCSI cycle wipes it
print("[restore IP + restart dnsmasq]")
subprocess.run(["sudo","ip","addr","add","10.42.1.1/24","dev","enx00e04c68016b"],
               capture_output=True)
subprocess.run(["sudo","ip","link","set","enx00e04c68016b","up"], capture_output=True)
subprocess.run(["uv","run","--no-project","python","tmp/netboot_server.py","start","openwrt-gale.itb"],
               capture_output=True, text=True, timeout=15)

# Start AP UART reader
ap_buf = []; stop = False
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
time.sleep(0.5)

# Power on (rely on GBB FORCE_DEV; explicitly clear rec/dev for cleanliness)
print("\n[T-boot: gale dev off, rec off, power on  (GBB FORCE_DEV will set dev mode)]")
ec("gale dev off")
ec("gale rec off")
ec("gale power on")

# Watch for gates over 120s (driver halt-fallback takes ~90s if PSGMII fails 3x)
print("[capturing AP UART for 120s — watching for gates]")
GATES = [
    ("T-A: bootblock",                  "bootblock start"),
    ("T-A: VbBootDeveloper",            "VbBootDeveloper"),
    ("T-A: VbBootRecovery (negative)",  "VbBootRecovery"),
    ("T-A: Body Digest fail (negative)","Digest check failed"),
    ("T-A: Starting netboot",           "Starting netboot on gale"),
    ("T-B: ipq4019: MAC",               "ipq4019: MAC"),
    ("T-B: MDIO probe (diagnostic)",    "ipq4019: MDIO addr"),
    ("T-B: PSGMII attempt",             "PSGMII"),
    ("T-B: PSGMII passed",              "self-test passed"),
    ("T-C: eth_init attempt 1/3",       "eth_init attempt 1/3"),
    ("T-C: eth_init attempt 2/3",       "eth_init attempt 2/3"),
    ("T-C: eth_init attempt 3/3",       "eth_init attempt 3/3"),
    ("T-C: HALT-FALLBACK (gave up)",    "giving up"),
    ("T-F: Driver completed init",      "net_add_device"),
    ("T-F: Driver waits for link",      "Waiting for"),
    ("T-F: link up",                    "link is up"),
    ("T-F: DHCPDISCOVER",               "DHCPDISCOVER"),
    ("T-F: TFTP openwrt",               "openwrt-gale.itb"),
    ("CRASH (negative)",                "Data Abort"),
]
seen = set()
t0 = time.time(); last_report = 0
while time.time() - t0 < 120:
    text = b"".join(ap_buf).decode("latin1","replace")
    for label, needle in GATES:
        if label not in seen and needle in text:
            elapsed = time.time() - t0
            seen.add(label)
            print(f"  t+{elapsed:5.1f}s  [{label}]")
    if "giving up" in text or "Data Abort" in text:
        # Driver done (good or bad) — stop early
        break
    if time.time() - last_report > 15:
        last_report = time.time()
        print(f"  ... t+{time.time()-t0:.0f}s, {len(seen)} gates so far")
    time.sleep(0.5)

stop = True; time.sleep(0.5)
text = b"".join(ap_buf).decode("latin1","replace")
lines = [l for l in text.splitlines() if l.strip()]
print(f"\n=== AP UART total: {len(lines)} lines ===")
print()
print("=== GATES (T-A through T-F) ===")
for label, needle in GATES:
    print(f"  [{'X' if label in seen else ' '}] {label}")

# Now T-D: try SuzyQ flashrom RDID in current AP state
print()
print("=== T-D: SuzyQ flashrom RDID in current post-boot AP state ===")
print("  (driver state: " +
      ("HALTED — should yield bus" if "giving up" in text else
       "RUNNING — may or may not yield bus") + ")")
ec("gale power off", w=1.2)
r = subprocess.run(["sudo","/usr/sbin/flashrom","-p","raiden_debug_spi",
                    "-c","W25Q64BV/W25Q64CV/W25Q64FV","--flash-name"],
                   capture_output=True, text=True, timeout=10)
ok = r.returncode == 0 and "Winbond" in (r.stdout + r.stderr)
print(f"  T-D result: {'PASS — SuzyQ ACCESSIBLE' if ok else 'FAIL — SuzyQ blocked'}")
for ln in (r.stdout+r.stderr).splitlines()[-4:]:
    print(f"  | {ln}")

# Also check LAST 20 lines of AP UART for diagnostics
print()
print("=== LAST 25 lines of AP UART ===")
for l in lines[-25:]:
    print(" >", l[:160])

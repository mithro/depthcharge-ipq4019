#!/usr/bin/env python3
"""Boot v21 with both NICs UP — show ALL PHY link states.
Verifies BOTH gale jacks have link partners on the laptop side."""
import subprocess, time, os, serial, threading

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"

def ec(c, w=0.4):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.15
    s.dtr = False; s.rts = False; s.open()
    s.write((c + "\r").encode()); s.flush(); time.sleep(w)
    s.read(8192); s.close()

# UCSI cycle
subprocess.run(["sudo", "sh", "-c",
    "echo 0x10003 > /sys/kernel/debug/usb/ucsi/USBC000:00/command"], check=True)
time.sleep(0.3)
while subprocess.run(["lsusb", "-d", "18d1:500f"],
                     capture_output=True, text=True).stdout:
    time.sleep(0.1)
for _ in range(100):
    if subprocess.run(["lsusb", "-d", "18d1:500f"],
                      capture_output=True, text=True).stdout:
        break
    time.sleep(0.1)
for _ in range(60):
    if os.path.exists(EC): break
    time.sleep(0.1)
time.sleep(3.0)

# Ensure both NICs are UP and have link
subprocess.run(["sudo","ip","link","set","enx00e04c68016b","up"], capture_output=True)
subprocess.run(["sudo","ip","link","set","enx00e04c360636","up"], capture_output=True)
# Re-add the dnsmasq IP on ...360636 (where dnsmasq is bound now)
subprocess.run(["sudo","ip","addr","add","10.42.1.1/24","dev","enx00e04c360636"],
               capture_output=True)
time.sleep(2)
# Print laptop NIC states for reference
print("[laptop NICs:]")
r = subprocess.run(["ip","-br","link","show"], capture_output=True, text=True)
for ln in r.stdout.splitlines():
    if "enx0" in ln:
        print(f"  {ln}")

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
time.sleep(0.4)

ec("gale dev off"); ec("gale rec off"); ec("gale power on")
print("[capture 60s]")
t0 = time.time()
while time.time() - t0 < 60:
    text = b"".join(ap_buf).decode("latin1", "replace")
    if "PHY 4" in text and "PHY_SPECIFIC" in text:
        time.sleep(1); break
    if "panic" in text or "Data Abort" in text:
        time.sleep(2); break
    time.sleep(0.5)

stop = True; time.sleep(0.5)
text = b"".join(ap_buf).decode("latin1", "replace")
lines = [l for l in text.splitlines() if l.strip()]

print("\n=== ALL PHY states (LAN = PHY 3, WAN = PHY 4) ===")
for l in lines:
    if "ipq4019: PHY " in l and "PHY_SPECIFIC" in l:
        print(f"  | {l[:200]}")
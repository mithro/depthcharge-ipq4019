#!/usr/bin/env python3
"""Test: bring laptop's ...68016b NIC DOWN AFTER UCSI cycle so gale's LAN jack
loses link and only WAN jack (PHY 4) has a link partner. Verify TFTP boot."""
import subprocess, time, os, serial, threading

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"

def ec(c, w=0.4):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.15
    s.dtr = False; s.rts = False; s.open()
    s.write((c + "\r").encode()); s.flush(); time.sleep(w)
    s.read(8192); s.close()

# UCSI cycle
print("[UCSI cycle]")
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
time.sleep(4.0)  # Wait for laptop NICs to re-enumerate too

# AGGRESSIVELY disable ...68016b on the laptop side (force gale's LAN to lose link)
print("[disabling ...68016b on laptop side]")
subprocess.run(["sudo","nmcli","device","set","enx00e04c68016b","managed","no"],
               capture_output=True)
subprocess.run(["sudo","ip","link","set","enx00e04c68016b","down"], capture_output=True)
# Ensure ...360636 stays UP with the dnsmasq IP
subprocess.run(["sudo","ip","link","set","enx00e04c360636","up"], capture_output=True)
subprocess.run(["sudo","ip","addr","add","10.42.1.1/24","dev","enx00e04c360636"],
               capture_output=True)
time.sleep(2)

print("[laptop NIC state:]")
r = subprocess.run(["ip","-br","link","show"], capture_output=True, text=True)
for ln in r.stdout.splitlines():
    if "enx0" in ln: print(f"  {ln}")

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

# Wait extra before powering AP — give PHY 4 time for cable peer to settle
print("[wait 3s for PHY peers to settle]")
time.sleep(3)

ec("gale dev off"); ec("gale rec off"); ec("gale power on")
print("[capture 180s]")
t0 = time.time()
while time.time() - t0 < 180:
    text = b"".join(ap_buf).decode("latin1", "replace")
    if "Link is Up - 1Gbps" in text and "qca8k" in text:
        time.sleep(8); break
    if "panic" in text or "Data Abort" in text:
        time.sleep(2); break
    if "giving up" in text:
        time.sleep(2); break
    time.sleep(0.5)

stop = True; time.sleep(0.5)
text = b"".join(ap_buf).decode("latin1", "replace")
lines = [l for l in text.splitlines() if l.strip()]
print()
print("=== KEY EVENTS ===")
for l in lines:
    if any(k in l for k in ("ipq4019: PHY ", "Sending DHCP", "Waiting for reply... done",
                            "bytes long", "Loading FIT", "Compat", "Choosing best",
                            "Exiting depthcharge", "qca8k-ipq4019",
                            "PSGMII calibration", "Link is Up", "Link is Down",
                            "panic", "Data Abort")):
        print(f"  | {l[:200]}")
#!/usr/bin/env python3
"""Test B: UCSI cycle gale, boot with v20, observe which PHY links and
verify full kernel boot. dnsmasq must already be running on ...360636."""
import subprocess, time, os, serial, threading

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"

def ec(c, w=0.4):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.15
    s.dtr = False; s.rts = False; s.open()
    s.write((c + "\r").encode()); s.flush(); time.sleep(w)
    s.read(8192); s.close()

# UCSI cycle to fully reset gale
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
time.sleep(2.0)

# Verify the netboot IP is on ...360636 (NOT ...68016b — that's down for Test B)
subprocess.run(["sudo","ip","addr","add","10.42.1.1/24","dev","enx00e04c360636"],
               capture_output=True)

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
print("[capture 180s; cable in WAN jack expected based on Test A finding LAN→...68016b]")
t0 = time.time()
while time.time() - t0 < 180:
    text = b"".join(ap_buf).decode("latin1", "replace")
    if "Link is Up - 1Gbps" in text or "panic" in text or "Data Abort" in text:
        time.sleep(8); break
    if "giving up" in text:
        time.sleep(2); break
    time.sleep(0.5)

stop = True; time.sleep(0.5)
text = b"".join(ap_buf).decode("latin1", "replace")
lines = [l for l in text.splitlines() if l.strip()]
print(f"\n=== {len(lines)} AP UART lines ===")
print()
print("=== KEY EVENTS ===")
for l in lines:
    if any(k in l for k in ("ipq4019: link up", "Sending DHCP", "done.",
                            "bytes long", "Loading FIT", "Image kernel",
                            "Image fdt", "Compat preference", "Choosing best",
                            "Exiting depthcharge", "qca8k-ipq4019",
                            "PSGMII calibration", "Link is Up", "Link is Down",
                            "panic", "Data Abort", "Modules linked")):
        print(f"  | {l[:200]}")
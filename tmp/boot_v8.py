#!/usr/bin/env python3
"""UCSI cycle, boot v7, capture full AP UART for 120s. Print everything."""
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
time.sleep(2.0)

# Re-add the netboot IP after UCSI drops the iface
subprocess.run(["sudo","ip","addr","add","10.42.1.1/24","dev","enx00e04c68016b"],
               capture_output=True)
subprocess.run(["sudo","ip","link","set","enx00e04c68016b","up"], capture_output=True)

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
print("[capture 120s]")
t0 = time.time()
while time.time() - t0 < 120:
    text = b"".join(ap_buf).decode("latin1", "replace")
    if "giving up" in text or "Data Abort" in text:
        time.sleep(2); break
    if "Starting kernel" in text:
        time.sleep(3); break
    time.sleep(0.5)

stop = True; time.sleep(0.5)
text = b"".join(ap_buf).decode("latin1", "replace")
lines = [l for l in text.splitlines() if l.strip()]

print(f"\n=== Full AP UART: {len(lines)} lines ===")

# Print interesting lines (not the MDIO addr spam)
print("\n=== INTERESTING LINES (filtered) ===")
for l in lines:
    if "MDIO addr" not in l:
        print(f"  | {l[:200]}")

# Print last 20 of everything for context
print("\n=== LAST 20 LINES ===")
for l in lines[-20:]:
    print(f"  > {l[:200]}")

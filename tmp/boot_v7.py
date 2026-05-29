#!/usr/bin/env python3
"""UCSI cycle, boot v5, capture AP UART. Watch for v5 diagnostics."""
import subprocess, time, os, serial, threading

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"

def ec(c, w=0.4):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.15
    s.dtr = False; s.rts = False; s.open()
    s.write((c + "\r").encode()); s.flush(); time.sleep(w)
    s.read(8192); s.close()

print("[UCSI CONNECTOR_RESET]")
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

print("[gale dev off, rec off, power on]")
ec("gale dev off"); ec("gale rec off"); ec("gale power on")

print("[capture AP UART for 30s, watching for v5 diagnostics]")
t0 = time.time()
while time.time() - t0 < 30:
    text = b"".join(ap_buf).decode("latin1", "replace")
    if "Data Abort" in text:
        break
    if "giving up" in text:
        time.sleep(2); break
    time.sleep(0.5)

stop = True; time.sleep(0.5)
text = b"".join(ap_buf).decode("latin1", "replace")
lines = [l for l in text.splitlines() if l.strip()]

print(f"\n=== AP UART {len(lines)} lines ===")
print()
print("=== v5 diagnostic lines ===")
for l in lines:
    if any(k in l for k in ("GCC_ESS_CBCR", "GCC_ESS_BCR", "GCC_ESS_PORT_ARES",
                            "per-port resets", "ESS clock",
                            "MDIO_MODE", "MDIO_ADDR", "MDIO_CMD",
                            "MATCHES", "MISMATCH", "all-1s", "all-0s",
                            "ipq4019_mdio", "ipq4019: MDIO addr",
                            "PSGMII", "self-test")):
        print(f"  | {l[:180]}")

#!/usr/bin/env python3
"""Fresh root-port cycle. Don't send any commands. Watch what the EC + AP do
automatically. Determine current device state with no interference."""
import subprocess, time, serial, os, threading
PORT = "/sys/bus/usb/devices/3-0:1.0/usb3-port1/disable"
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"

def present():
    return "18d1:500f" in subprocess.run(["lsusb"], capture_output=True, text=True).stdout
def setdis(v):
    subprocess.run(["sudo","sh","-c",f"echo {v} > {PORT}"], check=True)
def ec(c, w=0.5):
    s=serial.Serial(); s.port=EC; s.baudrate=115200; s.timeout=0.15
    s.dtr=False; s.rts=False; s.open()
    s.write((c+"\r").encode()); s.flush(); time.sleep(w)
    r=s.read(8192); s.close(); return r.decode("latin1","replace")

# Capture EC + AP from the moment they re-enumerate
ec_buf=[]; ap_buf=[]; stop=False
def reader(port, buf):
    while not stop:
        if not os.path.exists(port):
            time.sleep(0.1); continue
        try:
            s=serial.Serial(); s.port=port; s.baudrate=115200; s.timeout=0.1
            s.dtr=False; s.rts=False; s.open()
            while not stop:
                d=s.read(4096)
                if d: buf.append(d)
            s.close()
        except Exception:
            time.sleep(0.3)
threading.Thread(target=reader, args=(EC,ec_buf), daemon=True).start()
threading.Thread(target=reader, args=(AP,ap_buf), daemon=True).start()
time.sleep(0.3)

print("[cut power]"); setdis(1)
for _ in range(12):
    time.sleep(1)
    if not present(): break
time.sleep(5)
print("[restore power] -- NO commands sent, observe defaults --")
setdis(0)
print("[15s observation]")
time.sleep(15)
stop=True; time.sleep(0.4)

print("\n=== EC console (default boot output) ===")
ec_out=b"".join(ec_buf).decode("latin1","replace")
ec_lines=[l for l in ec_out.splitlines() if l.strip()]
print(f"  EC non-empty lines: {len(ec_lines)}")
for l in ec_lines[:25]:
    print(" e>",l[:140])
if len(ec_lines) > 25:
    for l in ec_lines[-5:]:
        print(" e>",l[:140])

print("\n=== AP console (does it boot?) ===")
ap_out=b"".join(ap_buf).decode("latin1","replace")
ap_lines=[l for l in ap_out.splitlines() if l.strip()]
print(f"  AP non-empty lines: {len(ap_lines)}")
for l in ap_lines[:25]:
    print(" a>",l[:140])

print("\n=== Final GPIO state (no commands) ===")
gp = ec("gpioget", 1.0)
for ln in gp.splitlines():
    s=ln.strip()
    if any(k in s for k in ("VDD_1P1_CPU","VDD_3P3","SYS_PWR","WP_L")):
        print(" ", s)

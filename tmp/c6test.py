#!/usr/bin/env python3
"""After 'reboot ap-off' (AP held in reset from power-on -> pads high-Z), power
the flash rail and test a read. This is the cleanest 'IPQ-in-reset + flash-on'."""
import serial, time, subprocess, os
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"

def ec(c, w=1.2):
    for _ in range(20):
        try:
            s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
            s.dtr = False; s.rts = False; s.open()
            s.write((c + "\r").encode()); s.flush(); time.sleep(w)
            r = s.read(8192); s.close(); return r.decode("latin1", "replace")
        except Exception:
            time.sleep(1)
    return "<no EC>"

# wait for re-enumeration
for _ in range(20):
    if os.path.exists(EC):
        break
    time.sleep(1)
time.sleep(2)
print("power state:", " ".join(l.strip() for l in ec("gale power").splitlines() if "power" in l.lower())[-40:])
ec("gpioset VDD_3P3_EN 1"); time.sleep(0.5)
gp = ec("gpioget")
for ln in gp.splitlines():
    if any(k in ln for k in ("VDD_3P3_EN", "VDD_1P1_CPU", "SYS_PWR", "WP_L")):
        print("  ", ln.strip())
r = subprocess.run(["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi", "-r",
                    "tmp/c6.bin", "--fmap", "-i", "FW_MAIN_A"],
                   capture_output=True, text=True, timeout=200)
for ln in (r.stdout + r.stderr).splitlines():
    if any(k in ln for k in ("Found", "done", "FAIL", "error")):
        print("  fr|", ln)
if os.path.exists("tmp/c6.bin"):
    d = open("tmp/c6.bin", "rb").read()
    print("  read zero% =", round(100*d.count(0)/max(len(d),1), 1), "(want <90)")

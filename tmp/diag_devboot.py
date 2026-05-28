#!/usr/bin/env python3
"""Force dev mode, reboot, CONFIRM the AP reaches a stable (non-crashing) boot,
then test whether the flash reads cleanly with the AP cleanly off."""
import subprocess, time, threading, serial, os

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"
FR = "/usr/sbin/flashrom"

def openp(p):
    s = serial.Serial(); s.port = p; s.baudrate = 115200; s.timeout = 0.1
    s.dtr = False; s.rts = False; s.open(); return s

def ec(cmd, w=1.0):
    try:
        s = openp(EC); s.write((cmd + "\r").encode()); s.flush(); time.sleep(w)
        r = s.read(8192); s.close(); return r.decode("latin1", "replace")
    except Exception as e:
        return f"<err {e}>"

print("dev on  ->", ec("gale dev on").strip()[-20:])
print("rec off ->", ec("gale rec off").strip()[-20:])

cap = []; stop = False
def reader():
    while not stop:
        try:
            s = openp(AP)
            while not stop:
                c = s.read(4096)
                if c: cap.append(c)
        except Exception:
            time.sleep(0.3)
threading.Thread(target=reader, daemon=True).start()

# reboot via a short-lived EC open (don't hold it)
try:
    s = openp(EC); s.write(b"reboot\r"); s.flush(); time.sleep(0.4); s.close()
except Exception:
    pass
print("[reboot; capturing 22s to confirm boot stability]")
time.sleep(22); stop = True; time.sleep(0.3)
txt = b"".join(cap).decode("latin1", "replace")
crashed = "Data Abort" in txt
mode = ("RECOVERY" if "VbBootRecovery" in txt else
        "DEVELOPER" if "VbBootDeveloper" in txt else
        "NETBOOT" if "Starting netboot" in txt else "?")
print(f"  boot mode={mode}  crashed={crashed}  reachedDC={'depthcharge on gale' in txt}")
print("  last AP lines:")
for ln in [l for l in txt.splitlines() if l.strip()][-6:]:
    print("   |", ln[:120])

print("[gale power off + clean read test]")
print("  ", ec("gale power off", 1.5).strip()[-20:])
time.sleep(4)
gp = ec("gpioget")
print("  ", " ".join(l.strip() for l in gp.splitlines() if "VDD_1P1_CPU" in l))
subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-r", "tmp/diagchk.bin",
                "--fmap", "-i", "FW_MAIN_A"], capture_output=True, text=True, timeout=200)
if os.path.exists("tmp/diagchk.bin"):
    d = open("tmp/diagchk.bin", "rb").read()
    print(f"  flash read zero% = {100*d.count(0)/max(len(d),1):.1f}  (want <90)")

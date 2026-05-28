#!/usr/bin/env python3
"""Robust RW flash: get the AP to a STABLE state (clear recovery so it boots the
non-crashing stock RW dev screen), let it settle, then clean power-off + flash
FW_MAIN_A. Avoids the hung-AP bus contention that fails the erase."""
import subprocess, time, serial, sys

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/usr/sbin/flashrom"
IMG = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-netboot-rw.bin"
REGION = sys.argv[1] if len(sys.argv) > 1 else "FW_MAIN_A"

def ec(cmd, wait=1.0):
    try:
        s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
        s.dtr = False; s.rts = False; s.open()
        s.write((cmd + "\r").encode()); s.flush(); time.sleep(wait)
        r = s.read(8192); s.close(); return r.decode("latin1", "replace")
    except Exception as e:
        return f"<err {e}>"

print("rec off ->", ec("gale rec off").strip()[-30:])
print("reboot (clean AP reset -> stable stock RW dev screen)")
ec("reboot", 0.5)
time.sleep(18)                      # let AP boot to the stable (non-crashing) dev screen
print("gale power off ->", ec("gale power off").strip()[-30:])
gp = ec("gpioget")
for ln in gp.splitlines():
    if "VDD_1P1_CPU" in ln:
        print("   ", ln.strip(), "(want 0 = CPU off)")
print(f"flashrom -w -i {REGION}")
t0 = time.time()
r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-w", IMG, "--fmap", "-i", REGION],
                   capture_output=True, text=True, timeout=400)
for ln in (r.stdout + r.stderr).splitlines():
    if any(k in ln for k in ("Found", "Erasing", "Writing", "Verifying", "VERIFIED",
                             "FAILED", "Error", "done")):
        print("   |", ln)
print("[exit %d, %.0fs] RESULT: %s" % (r.returncode, time.time()-t0,
      "SUCCESS" if r.returncode == 0 else "FAILED"))

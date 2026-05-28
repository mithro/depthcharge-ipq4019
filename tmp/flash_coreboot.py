#!/usr/bin/env python3
"""Flash the COREBOOT region (Approach B) over SuzyQ: AP off + WP deasserted,
single atomic flashrom write of -i COREBOOT, verified. Restore = stock dump."""
import subprocess, time, serial, sys

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/usr/sbin/flashrom"
IMG = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-netboot-ro.bin"

def ec(cmd, wait=1.2):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
    s.dtr = False; s.rts = False; s.open()
    s.write((cmd + "\r").encode()); s.flush(); time.sleep(wait)
    r = s.read(8192); s.close(); return r.decode("latin1", "replace")

print("[1] AP off (free SPI bus)"); print("   ", ec("gale power off").strip()[-50:])
print("[2] deassert WP (gpioset WP_L 1)"); ec("gpioset WP_L 1")
gp = ec("gpioget")
for ln in gp.splitlines():
    if "WP_L" in ln or "VDD_1P1_CPU" in ln:
        print("   ", ln.strip())
if not any("1" in ln and "WP_L" in ln for ln in gp.splitlines()):
    print("   WARNING: WP_L not confirmed high")

print("[3] flashrom -w -i COREBOOT (single atomic run, with verify)")
t0 = time.time()
r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-w", IMG,
                    "--fmap", "-i", "COREBOOT"],
                   capture_output=True, text=True, timeout=400)
out = r.stdout + r.stderr
for ln in out.splitlines():
    if any(k in ln for k in ("Found", "Erasing", "Writing", "Verifying",
                             "VERIFIED", "verified", "FAILED", "Error", "error",
                             "protected", "done", "match")):
        print("   |", ln)
print("[exit %d, %.0fs]" % (r.returncode, time.time()-t0))
print("RESULT:", "SUCCESS" if r.returncode == 0 else "FAILED - restore stock if needed")

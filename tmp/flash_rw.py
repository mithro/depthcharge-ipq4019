#!/usr/bin/env python3
"""Flash FW_MAIN_A (RW, outside WP_RO) over SuzyQ: AP off, single atomic
flashrom write, verified. No WP deassert needed."""
import subprocess, time, serial, sys

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/usr/sbin/flashrom"
IMG = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-netboot-rw.bin"
REGION = sys.argv[1] if len(sys.argv) > 1 else "FW_MAIN_A"

def ec(cmd, wait=1.2):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
    s.dtr = False; s.rts = False; s.open()
    s.write((cmd + "\r").encode()); s.flush(); time.sleep(wait)
    r = s.read(8192); s.close(); return r.decode("latin1", "replace")

print("[1] AP off:", ec("gale power off").strip()[-40:])
print(f"[2] flashrom -w -i {REGION} (verify)")
t0 = time.time()
r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-w", IMG,
                    "--fmap", "-i", REGION],
                   capture_output=True, text=True, timeout=400)
for ln in (r.stdout + r.stderr).splitlines():
    if any(k in ln for k in ("Found", "Erasing", "Writing", "Verifying",
                             "VERIFIED", "FAILED", "Error", "error", "done")):
        print("   |", ln)
print("[exit %d, %.0fs]" % (r.returncode, time.time()-t0))
print("RESULT:", "SUCCESS" if r.returncode == 0 else "FAILED")

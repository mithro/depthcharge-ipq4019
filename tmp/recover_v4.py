#!/usr/bin/env python3
"""Read v4 back from the device via SuzyQ (correct procedure)."""
import subprocess, time, serial, hashlib

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
OUT = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-netboot-v4.bin"

def ec(cmd, wait=1.2):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
    s.dtr = False; s.rts = False; s.open()
    s.write(b"\r"); time.sleep(0.2); s.read(8192)
    s.write((cmd + "\r").encode()); s.flush()
    time.sleep(wait)
    out = s.read(8192).decode("latin1", "replace")
    s.close()
    return out

print("[1] gale power off")
print(ec("gale power off"))

print("[2] SuzyQ read (8 MiB, ~45s)")
t0 = time.time()
r = subprocess.run(["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
                    "-r", OUT], capture_output=True, text=True, timeout=200)
print(f"  exit={r.returncode}  elapsed={time.time()-t0:.0f}s")
for ln in (r.stdout + r.stderr).splitlines():
    if any(k in ln for k in ("Found", "Reading", "done", "Error")):
        print(f"  | {ln}")

d = open(OUT, "rb").read()
print(f"\nsize: {len(d)} bytes  sha256: {hashlib.sha256(d).hexdigest()}")

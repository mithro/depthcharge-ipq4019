#!/usr/bin/env python3
"""Procedure per gale-spi-flash-backup.md:
1. gale power off
2. SINGLE atomic flashrom -r (no -c, no prior probes)
3. flashrom re-powers AP on exit → don't probe before reading.

Test: read full chip via raiden_debug_spi with no JEDEC match override,
verify against known stock + freshly flashed v3.
"""
import subprocess, time, serial, hashlib, os

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
OUT = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/correct_suzyq_dump.bin"

def ec_cmd(cmd, wait=1.2):
    s = serial.Serial()
    s.port = EC; s.baudrate = 115200; s.timeout = 0.2
    s.dtr = False; s.rts = False
    s.open()
    s.write(b"\r"); time.sleep(0.2); s.read(8192)
    s.write((cmd + "\r").encode()); s.flush()
    time.sleep(wait)
    out = s.read(8192).decode("latin1", "replace")
    s.close()
    return out

# Single atomic operation: power off + read
print("[1] gale power off")
print(ec_cmd("gale power off"))

print("[2] flashrom -p raiden_debug_spi -r (SFDP, no -c)")
t0 = time.time()
r = subprocess.run(["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
                    "-r", OUT],
                   capture_output=True, text=True, timeout=300)
elapsed = time.time() - t0
print(f"  exit={r.returncode}  elapsed={elapsed:.1f}s")
for ln in (r.stdout + r.stderr).splitlines():
    if any(k in ln for k in ("Found", "SFDP", "Reading", "done", "Error",
                              "error", "Unknown", "kB,")):
        print(f"  | {ln}")

if os.path.exists(OUT):
    size = os.path.getsize(OUT)
    print(f"\n  Dump size: {size} bytes")
    if size == 8 * 1024 * 1024:
        h = hashlib.sha256(open(OUT, "rb").read()).hexdigest()
        print(f"  sha256: {h}")
        # Compare to v3 (last CH341A flash) and stock
        for label, path in [
            ("v3.bin (last CH341A flash)",
             "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-netboot-v3.bin"),
            ("stock 2026-05-28",
             "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"),
        ]:
            if os.path.exists(path):
                ref = hashlib.sha256(open(path, "rb").read()).hexdigest()
                print(f"  vs {label}: {'MATCH' if h == ref else 'differ'}  ({ref[:16]}..)")

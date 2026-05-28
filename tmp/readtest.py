#!/usr/bin/env python3
"""Find the working SuzyQ read state: AP held off (reboot ap-off) + flash rail
powered (gpioset VDD_3P3_EN 1), then a SINGLE cros-flashrom -r of the whole chip."""
import time, subprocess, serial, os

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/home/tim/local/gwifi/depthcharge-ipq4019/flashrom-cros/flashrom"
STOCK = "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"
OUT = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/fulldump.bin"

def ec(cmd, wait=1.0):
    try:
        s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
        s.dtr = False; s.rts = False; s.open()
        s.write((cmd + "\r").encode()); s.flush(); time.sleep(wait)
        r = s.read(8192); s.close(); return r.decode("latin1", "replace")
    except Exception as e:
        return f"<err {e}>"

print("reboot ap-off ->", ec("reboot ap-off", 1.0).strip()[:40])
print("[wait 13s re-enum]"); time.sleep(13)
print("gpioset VDD_3P3_EN 1 ->", ec("gpioset VDD_3P3_EN 1", 1.0).strip()[-40:])
gp = ec("gpioget", 1.5)
for ln in gp.splitlines():
    if any(k in ln for k in ("WP_L", "VDD_3P3_EN", "VDD_1P1_CPU", "SYS_PWR")):
        print("  ", ln.strip())

print("[single flashrom -r of whole chip, AP held off + rail powered]")
t0 = time.time()
try:
    r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-r", OUT],
                       capture_output=True, text=True, timeout=400)
    for ln in (r.stdout + r.stderr).splitlines()[-10:]:
        print("  |", ln)
    print("flashrom exit:", r.returncode, "elapsed %.0fs" % (time.time()-t0))
except subprocess.TimeoutExpired:
    print("  flashrom TIMED OUT")

if os.path.exists(OUT) and os.path.getsize(OUT) > 0:
    a = open(OUT, "rb").read(); b = open(STOCK, "rb").read()
    n = min(len(a), len(b))
    same = sum(1 for i in range(0, n, 64) if a[i] == b[i])  # sample every 64B
    print(f"read size={len(a)} stock={len(b)}  sampled match={100*same/(n//64):.1f}%")
    print("read [0:16] :", a[:16].hex(' '))
    print("stock[0:16] :", b[:16].hex(' '))
else:
    print("no/empty output")

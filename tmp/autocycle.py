#!/usr/bin/env python3
"""Autonomous: wait for the manual power-cycle, then immediately quiesce the AP
and flash the FIXED netboot driver into FW_MAIN_A (RW) + set dev mode. Exits
(notifies) with the result so the main session does the reboot+capture."""
import subprocess, time, serial, os

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/usr/sbin/flashrom"
IMG = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-netboot-rw.bin"
DEV = "18d1:500f"

def present():
    return DEV in subprocess.run(["lsusb"], capture_output=True, text=True).stdout

def ec(cmd, wait=0.4):
    try:
        s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
        s.dtr = False; s.rts = False; s.open()
        s.write((cmd + "\r").encode()); s.flush(); time.sleep(wait)
        r = s.read(8192); s.close(); return r.decode("latin1", "replace")
    except Exception:
        return ""

T0 = time.time(); TIMEOUT = 2400
print("ARMED: waiting for power cut (gale USB to disappear)...", flush=True)
while present() and time.time()-T0 < TIMEOUT:
    time.sleep(1)
if present():
    print("TIMEOUT: no power-cycle seen"); raise SystemExit(0)
print("power cut detected; waiting for restore...", flush=True)
while not present() and time.time()-T0 < TIMEOUT:
    time.sleep(0.5)
# 1) AGGRESSIVELY hold AP off, starting the instant USB is back, to beat the
#    crashing-v1 boot that would re-stick the flash.
print("RESTORED: quiescing AP...", flush=True)
for _ in range(14):
    ec("gale power off", 0.35)
    time.sleep(0.25)
time.sleep(2)
# 2) verify flash responds
subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-r", "tmp/ac_chk.bin",
                "--fmap", "-i", "FW_MAIN_A"], capture_output=True, text=True, timeout=200)
ok = False
if os.path.exists("tmp/ac_chk.bin"):
    d = open("tmp/ac_chk.bin","rb").read(); zr = 100*d.count(0)/max(len(d),1)
    print(f"flash read zero%={zr:.1f}", flush=True); ok = zr < 90
if not ok:
    print("RESULT: flash still unresponsive after power-cycle"); raise SystemExit(0)
# 3) flash fixed driver into RW
print("flashing FIXED driver -> FW_MAIN_A ...", flush=True)
r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-w", IMG, "--fmap", "-i", "FW_MAIN_A"],
                   capture_output=True, text=True, timeout=400)
verified = "VERIFIED" in (r.stdout + r.stderr)
print("flash rc", r.returncode, "verified", verified, flush=True)
if r.returncode == 0:
    ec("gale dev on"); ec("gale rec off")
    print("RESULT: FIXED DRIVER FLASHED + dev mode set. Ready for reboot+capture.")
else:
    print("RESULT: flash write failed:", (r.stdout+r.stderr).splitlines()[-1] if (r.stdout+r.stderr) else "?")

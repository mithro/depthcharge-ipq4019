#!/usr/bin/env python3
"""Restore FW_MAIN_B from v3.bin via SuzyQ. Single atomic gale-power-off
+ flashrom -w. Proves write+verify works."""
import subprocess, time, serial

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
V3 = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-netboot-v3.bin"

def ec_cmd(cmd, wait=1.2):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
    s.dtr = False; s.rts = False; s.open()
    s.write(b"\r"); time.sleep(0.2); s.read(8192)
    s.write((cmd + "\r").encode()); s.flush()
    time.sleep(wait)
    out = s.read(8192).decode("latin1", "replace")
    s.close()
    return out

print("[1] gale power off")
print(ec_cmd("gale power off"))

print("[2] flashrom -w v3.bin --fmap -i FW_MAIN_B  (verify after write)")
t0 = time.time()
r = subprocess.run(["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
                    "-w", V3, "--fmap", "-i", "FW_MAIN_B"],
                   capture_output=True, text=True, timeout=400)
print(f"  exit={r.returncode}  elapsed={time.time()-t0:.0f}s")
for ln in (r.stdout + r.stderr).splitlines():
    if any(k in ln for k in ("Found", "SFDP", "Erasing", "Writing", "Verifying",
                             "VERIFIED", "done", "Error", "error", "FAILED")):
        print(f"  | {ln}")

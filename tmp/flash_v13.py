#!/usr/bin/env python3
"""Flash v5: atomic gale-power-off + flashrom -w v5.bin --fmap -i FW_MAIN_A
-i FW_MAIN_B -i VBLOCK_A -i VBLOCK_B (no -c, no probe)."""
import subprocess, time, serial, hashlib

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
IMG = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-netboot-v13.bin"

d = open(IMG, "rb").read()
print(f"v13.sha256: {hashlib.sha256(d).hexdigest()}")
assert len(d) == 8 * 1024 * 1024

def ec(cmd, wait=1.2):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
    s.dtr = False; s.rts = False; s.open()
    s.write(b"\r"); time.sleep(0.2); s.read(8192)
    s.write((cmd + "\r").encode()); s.flush(); time.sleep(wait)
    out = s.read(8192).decode("latin1", "replace")
    s.close()
    return out

print("[1] gale power off")
print(ec("gale power off"))

print("[2] flashrom -w v5.bin --fmap -i FW_MAIN_A -i FW_MAIN_B -i VBLOCK_A -i VBLOCK_B")
t0 = time.time()
r = subprocess.run(["sudo", "/usr/sbin/flashrom", "-p", "raiden_debug_spi",
                    "-w", IMG, "--fmap",
                    "-i", "FW_MAIN_A", "-i", "FW_MAIN_B",
                    "-i", "VBLOCK_A", "-i", "VBLOCK_B"],
                   capture_output=True, text=True, timeout=400)
print(f"  exit={r.returncode}  elapsed={time.time()-t0:.0f}s")
for ln in (r.stdout + r.stderr).splitlines():
    if any(k in ln for k in ("Found", "SFDP", "Erasing", "Writing", "Verifying",
                              "VERIFIED", "done", "Error", "error", "FAILED")):
        print(f"  | {ln}")
print("FLASH SUCCESS" if r.returncode == 0 else "FLASH FAILED")

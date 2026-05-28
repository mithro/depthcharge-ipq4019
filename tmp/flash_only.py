#!/usr/bin/env python3
"""Force-power ONLY the flash rail (VDD_3P3_EN=1) with the AP cleanly off.
This should give the EC SPI bridge a clean bus with no IPQ contention."""
import subprocess, time, serial, os
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/usr/sbin/flashrom"
CHIP = "W25Q64BV/W25Q64CV/W25Q64FV"

def ec(c, w=0.5):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.15
    s.dtr = False; s.rts = False; s.open()
    s.write((c + "\r").encode()); s.flush(); time.sleep(w)
    r = s.read(8192); s.close(); return r.decode("latin1", "replace")

# Ensure AP off
print("=== ensure AP off ===")
ec("gale power off", 1.5); time.sleep(2)
# Force flash rail on
print("=== gpioset VDD_3P3_EN 1 ===")
print(ec("gpioset VDD_3P3_EN 1", 0.5).strip()[-80:])
time.sleep(0.5)
# Also set WP_L=1 (deassert WP, allow COREBOOT writes)
ec("gpioset WP_L 1", 0.5)
time.sleep(0.5)
# Verify
print("=== verify GPIO state ===")
gp = ec("gpioget", 1.0)
for ln in gp.splitlines():
    s = ln.strip()
    if any(k in s for k in ("VDD_1P1_CPU","VDD_3P3","SYS_PWR","WP_L")):
        print(" ", s)
# Read flash
print("=== flash read test ===")
r = subprocess.run(["sudo",FR,"-p","raiden_debug_spi","-c",CHIP,"-r","tmp/fo.bin",
                    "-l","tmp/layout.txt","-i","COREBOOT"],
                   capture_output=True,text=True,timeout=200)
print(f"  flashrom rc={r.returncode}")
print("  --- last 10 lines stdout+stderr ---")
for ln in (r.stdout + r.stderr).splitlines()[-10:]:
    print("  |", ln)
if os.path.exists("tmp/fo.bin"):
    d = open("tmp/fo.bin","rb").read()
    z = 100*d.count(0)/max(len(d),1); f = 100*d.count(0xff)/max(len(d),1)
    print(f"  read len={len(d)} zero%={z:.1f} ff%={f:.1f}")
    print("  first 64 bytes hex:", d[:64].hex())
    print("  bytes 0x100-0x140:", d[0x100:0x140].hex())
else:
    print("  (no file written)")

#!/usr/bin/env python3
"""Run right after the gale power-cycle: aggressively hold the AP off (before it
can boot the crashing v1 and re-degrade the flash), confirm the flash responds,
then flash the FIXED netboot driver into FW_MAIN_A (RW), set dev mode, reboot."""
import subprocess, time, serial, os

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/usr/sbin/flashrom"
IMG = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-netboot-rw.bin"

def ec(cmd, wait=0.4):
    try:
        s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.2
        s.dtr = False; s.rts = False; s.open()
        s.write((cmd + "\r").encode()); s.flush(); time.sleep(wait)
        r = s.read(8192); s.close(); return r.decode("latin1", "replace")
    except Exception as e:
        return f"<err {e}>"

print("[1] hold AP off aggressively (catch before crash)")
for _ in range(8):
    ec("gale power off", 0.4)
    time.sleep(0.3)
time.sleep(2)
gp = ec("gpioget", 1.2)
for ln in gp.splitlines():
    if "VDD_1P1_CPU" in ln: print("   ", ln.strip())

print("[2] verify flash responds (read 64K @ 0x402000)")
r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-r", "tmp/postchk.bin",
                    "--fmap", "-i", "FW_MAIN_A"], capture_output=True, text=True, timeout=200)
ok = False
if os.path.exists("tmp/postchk.bin"):
    d = open("tmp/postchk.bin", "rb").read()
    zr = 100*d.count(0)/max(len(d),1)
    print(f"   read zero%={zr:.1f}")
    ok = zr < 90
print("   flash responds:", ok)

if ok:
    print("[3] flash FIXED netboot -> FW_MAIN_A (RW)")
    r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-w", IMG, "--fmap", "-i", "FW_MAIN_A"],
                       capture_output=True, text=True, timeout=400)
    for ln in (r.stdout+r.stderr).splitlines():
        if any(k in ln for k in ("Erasing","Verifying","VERIFIED","FAILED","Found")):
            print("   |", ln)
    print("   flash rc:", r.returncode)
    if r.returncode == 0:
        print("[4] dev on, rec off")
        ec("gale dev on"); ec("gale rec off")
        print("DONE: reboot+capture next")
else:
    print("FLASH STILL UNRESPONSIVE after power-cycle - may need a longer power-off or another cycle")

#!/usr/bin/env python3
"""Root-port power-cycle + catch the AP off BEFORE v1 crashes (clean bus release),
then flash the FIXED v2 into the COREBOOT/RO payload (where the device boots from)."""
import subprocess, time, serial, os
PORT = "/sys/bus/usb/devices/3-0:1.0/usb3-port1/disable"
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/usr/sbin/flashrom"
ROIMG = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/gale-netboot-ro.bin"

def present():
    return "18d1:500f" in subprocess.run(["lsusb"], capture_output=True, text=True).stdout
def setdis(v):
    subprocess.run(["sudo","sh","-c",f"echo {v} > {PORT}"], check=True)
def ec(cmd):
    try:
        s=serial.Serial(); s.port=EC; s.baudrate=115200; s.timeout=0.15
        s.dtr=False; s.rts=False; s.open(); s.write((cmd+"\r").encode()); s.flush()
        time.sleep(0.15); s.read(2048); s.close(); return True
    except Exception:
        return False

import threading
CHIP = "W25Q64BV/W25Q64CV/W25Q64FV"
hold = {"run": False, "sends": 0}
def ap_holder():
    """Persistent serial connection — no open/close overhead, hammers every 0.1s."""
    s = None
    while hold["run"]:
        try:
            if s is None:
                s = serial.Serial()
                s.port = EC; s.baudrate = 115200; s.timeout = 0.05
                s.dtr = False; s.rts = False
                s.open()
                s.read(8192)  # drain stale
            s.write(b"gale power off\r"); s.flush()
            hold["sends"] += 1
        except Exception:
            try:
                if s: s.close()
            except Exception:
                pass
            s = None
            time.sleep(0.3)
            continue
        time.sleep(0.1)
    if s:
        try: s.close()
        except Exception: pass

print("[cut power]"); setdis(1)
for _ in range(12):
    time.sleep(1)
    if not present(): break
time.sleep(4)
print("[restore power]"); setdis(0)
# Wait for the EC tty to enumerate; then start the persistent-serial hold thread.
for _ in range(30):
    if os.path.exists(EC): break
    time.sleep(0.2)
# Send WP_L=1 once via short connection BEFORE starting the hold (which will
# monopolize the EC serial port).
ec("gpioset WP_L 1")
print("[starting persistent-serial AP-hold thread (every 0.1s)]")
hold["run"] = True
threading.Thread(target=ap_holder, daemon=True).start()
time.sleep(4)  # let the hold thread settle and hammer ~40 'gale power off'
print(f"  hold sends so far: {hold['sends']}")
print("[read test: COREBOOT region, hold thread active]")
subprocess.run(["sudo",FR,"-p","raiden_debug_spi","-c",CHIP,"-r","tmp/cc_chk.bin",
                "-l","tmp/layout.txt","-i","COREBOOT"],
               capture_output=True,text=True,timeout=200)
ok=False
if os.path.exists("tmp/cc_chk.bin"):
    d=open("tmp/cc_chk.bin","rb").read(); zr=100*d.count(0)/max(len(d),1)
    print(f"  read zero%={zr:.1f}  (hold sends={hold['sends']})"); ok = zr < 80
if not ok:
    hold["run"] = False
    print("RESULT: flash not accessible (catch failed)"); raise SystemExit(0)
print("[flash FIXED v2 -> COREBOOT, hold still active]")
r=subprocess.run(["sudo",FR,"-p","raiden_debug_spi","-c",CHIP,"-w",ROIMG,
                  "-l","tmp/layout.txt","-i","COREBOOT"],
                 capture_output=True,text=True,timeout=400)
hold["run"] = False; time.sleep(1)
print(f"  final hold sends: {hold['sends']}")
print("  --- flashrom write output ---")
for ln in (r.stdout+r.stderr).splitlines()[-14:]:
    print("  |",ln)
print("RESULT:", "v2 FLASHED to COREBOOT (VERIFIED)" if r.returncode==0 and "VERIFIED" in (r.stdout+r.stderr) else f"flash rc={r.returncode}")

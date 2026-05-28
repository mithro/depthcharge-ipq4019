#!/usr/bin/env python3
"""Explicitly power the AP on with 'gale power on'. Observe whether it boots,
hangs in bootrom (COREBOOT corrupted), or boots fully (COREBOOT intact)."""
import subprocess, time, serial, os, threading
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"
FR = "/usr/sbin/flashrom"
CHIP = "W25Q64BV/W25Q64CV/W25Q64FV"

def ec(c, w=0.5):
    try:
        s=serial.Serial(); s.port=EC; s.baudrate=115200; s.timeout=0.15
        s.dtr=False; s.rts=False; s.open()
        s.write((c+"\r").encode()); s.flush(); time.sleep(w)
        r=s.read(8192); s.close(); return r.decode("latin1","replace")
    except Exception as e:
        return f"<err {e}>"

# Start AP console capture FIRST
buf=[]; stop=False
def reader():
    while not stop:
        try:
            a=serial.Serial(); a.port=AP; a.baudrate=115200; a.timeout=0.1
            a.dtr=False; a.rts=False; a.open()
            while not stop:
                d=a.read(4096)
                if d: buf.append(d)
            a.close()
        except Exception:
            time.sleep(0.3)
threading.Thread(target=reader, daemon=True).start()
time.sleep(0.3)

print("[gale power on]")
print(ec("gale power on", 1.5).strip()[-80:])
print("[observing 10s of AP boot]")
time.sleep(10)
stop=True; time.sleep(0.3)
out=b"".join(buf).decode("latin1","replace")
lines=[l for l in out.splitlines() if l.strip()]
print(f"  AP non-empty lines: {len(lines)}")
for l in lines[:15]:
    print("  >",l[:140])
if len(lines) > 15:
    print(f"  ...({len(lines)-20} omitted)...")
    for l in lines[-5:]:
        print("  >",l[:140])

# Check the AP state via EC GPIOs
print("\n[EC GPIO state]")
gp = ec("gpioget", 1.0)
for ln in gp.splitlines():
    s=ln.strip()
    if any(k in s for k in ("VDD_1P1_CPU","VDD_3P3","SYS_PWR","WP_L")):
        print(" ", s)

# Try flash read while AP is in its current state (may be in bootrom/SAHARA/crashed/boot)
print("\n[flash read attempt: AP-on, current state]")
r = subprocess.run(["sudo",FR,"-p","raiden_debug_spi","-c",CHIP,"-r","tmp/ao.bin",
                    "-l","tmp/layout.txt","-i","COREBOOT"],
                   capture_output=True,text=True,timeout=200)
print(f"  rc={r.returncode}")
for ln in (r.stdout+r.stderr).splitlines()[-6:]:
    print("  |",ln)
if os.path.exists("tmp/ao.bin"):
    d=open("tmp/ao.bin","rb").read()
    z=100*d.count(0)/max(len(d),1); f=100*d.count(0xff)/max(len(d),1)
    print(f"  zero%={z:.1f} ff%={f:.1f}  first 32: {d[:32].hex()}")

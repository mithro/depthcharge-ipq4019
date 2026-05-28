#!/usr/bin/env python3
"""Power-cycle via root port, then observe what the device does. Did the failed
erase corrupt COREBOOT? Does the IPQ now refuse to boot (= bus clean)?"""
import subprocess, time, serial, os, threading
PORT = "/sys/bus/usb/devices/3-0:1.0/usb3-port1/disable"
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"
FR = "/usr/sbin/flashrom"
CHIP = "W25Q64BV/W25Q64CV/W25Q64FV"

def present():
    return "18d1:500f" in subprocess.run(["lsusb"], capture_output=True, text=True).stdout
def setdis(v):
    subprocess.run(["sudo","sh","-c",f"echo {v} > {PORT}"], check=True)
def ec(c, w=0.5):
    try:
        s=serial.Serial(); s.port=EC; s.baudrate=115200; s.timeout=0.15
        s.dtr=False; s.rts=False; s.open()
        s.write((c+"\r").encode()); s.flush(); time.sleep(w)
        r=s.read(8192); s.close(); return r.decode("latin1","replace")
    except Exception as e:
        return f"<err {e}>"

print("[cut power]"); setdis(1)
for _ in range(12):
    time.sleep(1)
    if not present(): break
time.sleep(4)
print("[restore power]"); setdis(0)

# Wait for EC tty
for _ in range(40):
    if os.path.exists(EC): break
    time.sleep(0.2)
print(f"  EC tty present after wait: {os.path.exists(EC)}")

# Start AP console capture
buf=[]; stop_cap=False
def reader():
    while not stop_cap:
        try:
            a=serial.Serial(); a.port=AP; a.baudrate=115200; a.timeout=0.1
            a.dtr=False; a.rts=False; a.open()
            while not stop_cap:
                d=a.read(4096)
                if d: buf.append(d)
            a.close()
        except Exception:
            time.sleep(0.3)
threading.Thread(target=reader, daemon=True).start()

# Let the device do whatever it does for 10s
print("[observe 10s — what does the AP do?]")
time.sleep(10)

stop_cap=True; time.sleep(0.3)
ap_out=b"".join(buf).decode("latin1","replace")
lines=[l for l in ap_out.splitlines() if l.strip()]
print(f"  AP non-empty lines: {len(lines)}")
for l in lines[:10]:
    print("  >",l[:140])
if len(lines) > 10:
    print("  ...")
    for l in lines[-5:]:
        print("  >",l[:140])

print("\n[EC GPIO state after 10s]")
gp = ec("gpioget", 1.0)
for ln in gp.splitlines():
    s=ln.strip()
    if any(k in s for k in ("VDD_1P1_CPU","VDD_3P3","SYS_PWR","WP_L","AP_")):
        print(" ", s)

print("\n[flash read attempt: current state]")
r = subprocess.run(["sudo",FR,"-p","raiden_debug_spi","-c",CHIP,"-r","tmp/pc.bin",
                    "-l","tmp/layout.txt","-i","COREBOOT"],
                   capture_output=True,text=True,timeout=200)
print(f"  rc={r.returncode}")
for ln in (r.stdout+r.stderr).splitlines()[-8:]:
    print("  |",ln)
if os.path.exists("tmp/pc.bin"):
    d=open("tmp/pc.bin","rb").read()
    z=100*d.count(0)/max(len(d),1); f=100*d.count(0xff)/max(len(d),1)
    print(f"  zero%={z:.1f} ff%={f:.1f}")
    print("  first 32 bytes:", d[:32].hex())

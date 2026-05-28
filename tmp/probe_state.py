#!/usr/bin/env python3
"""After the failed/partial erase: check (a) the EC's view of GPIO state,
(b) what the AP is doing (any console output), (c) flash read contention."""
import subprocess, time, serial, os, threading
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"
FR = "/usr/sbin/flashrom"
CHIP = "W25Q64BV/W25Q64CV/W25Q64FV"

def ec(c, w=0.6):
    try:
        s=serial.Serial(); s.port=EC; s.baudrate=115200; s.timeout=0.15
        s.dtr=False; s.rts=False; s.open()
        s.write((c+"\r").encode()); s.flush(); time.sleep(w)
        r=s.read(8192); s.close(); return r.decode("latin1","replace")
    except Exception as e:
        return f"<err {e}>"

print("=== EC: current GPIO state ===")
gp = ec("gpioget", 1.0)
for ln in gp.splitlines():
    s = ln.strip()
    if any(k in s for k in ("VDD_1P1_CPU","VDD_3P3","SYS_PWR","WP_L","AP_")):
        print(" ", s)

print("\n=== AP console: 6s capture (is the AP doing anything?) ===")
buf=[]
def reader():
    try:
        a=serial.Serial(); a.port=AP; a.baudrate=115200; a.timeout=0.1
        a.dtr=False; a.rts=False; a.open()
        t0=time.time()
        while time.time()-t0 < 6:
            d=a.read(4096)
            if d: buf.append(d)
        a.close()
    except Exception as e:
        buf.append(f"<err {e}>".encode())
threading.Thread(target=reader).start()
time.sleep(6.5)
ap_out=b"".join(buf).decode("latin1","replace")
nonempty=[l for l in ap_out.splitlines() if l.strip()]
print(f"  AP non-empty lines: {len(nonempty)}")
for l in nonempty[-8:]:
    print(" |",l[:120])
crashed = "Data Abort" in ap_out
print(f"  contains 'Data Abort'={crashed}")

print("\n=== flash read test (no hold, no special) ===")
ec("gale power off", 1.5)
time.sleep(2)
gp2 = ec("gpioget", 1.0)
for ln in gp2.splitlines():
    s = ln.strip()
    if "VDD_1P1_CPU" in s or "VDD_3P3" in s:
        print(" ", s)
subprocess.run(["sudo",FR,"-p","raiden_debug_spi","-c",CHIP,"-r","tmp/probe.bin",
                "-l","tmp/layout.txt","-i","COREBOOT"],
               capture_output=True,text=True,timeout=200)
if os.path.exists("tmp/probe.bin"):
    d=open("tmp/probe.bin","rb").read()
    z=100*d.count(0)/max(len(d),1); f=100*d.count(0xff)/max(len(d),1)
    print(f"  read len={len(d)} zero%={z:.1f} ff%={f:.1f}")
    # If majority is 0xff -> chip is erased (good, we can re-flash cleanly).
    # If majority is 0x00 -> still contended OR chip has zeros from boot code.
    print("  first 64 bytes hex:", d[:64].hex())

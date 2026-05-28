#!/usr/bin/env python3
"""Read the FMAP region (4 KB @ 0x300000) in the catch state and compare
byte-for-byte to the stock dump. Untouched by the failed erase, so any
mismatch is purely a bus-fidelity issue (not real corruption of that region).

Read 3 times + per-byte vote: if the chip really is on the bus during clean
windows, a per-byte majority across reads should converge on the stock bytes."""
import subprocess, time, serial, os, threading
PORT = "/sys/bus/usb/devices/3-0:1.0/usb3-port1/disable"
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/usr/sbin/flashrom"
CHIP = "W25Q64BV/W25Q64CV/W25Q64FV"
STOCK = "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"

def present():
    return "18d1:500f" in subprocess.run(["lsusb"], capture_output=True, text=True).stdout
def setdis(v):
    subprocess.run(["sudo","sh","-c",f"echo {v} > {PORT}"], check=True)

hold = {"run": False}
def ap_holder():
    s = None
    while hold["run"]:
        try:
            if s is None:
                s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.05
                s.dtr = False; s.rts = False; s.open(); s.read(8192)
            s.write(b"gale power off\r"); s.flush()
        except Exception:
            try:
                if s: s.close()
            except: pass
            s = None; time.sleep(0.3); continue
        time.sleep(0.1)
    if s:
        try: s.close()
        except: pass

# Power-cycle to get a known starting point
print("[cut power]"); setdis(1)
for _ in range(12):
    time.sleep(1)
    if not present(): break
time.sleep(4)
print("[restore power]"); setdis(0)
for _ in range(30):
    if os.path.exists(EC): break
    time.sleep(0.2)
print("[start hold thread]")
hold["run"] = True
threading.Thread(target=ap_holder, daemon=True).start()
time.sleep(4)

# Stock FMAP slice
stock_fmap = open(STOCK,"rb").read()[0x300000:0x301000]
print(f"[stock FMAP slice: {len(stock_fmap)} bytes, signature: {stock_fmap[:8]!r}]")

reads = []
for n in range(3):
    p = f"tmp/fmapread_{n}.bin"
    if os.path.exists(p): os.unlink(p)
    print(f"[read #{n+1}: FMAP region]")
    r = subprocess.run(["sudo",FR,"-p","raiden_debug_spi","-c",CHIP,"-r",p,
                        "-l","tmp/layout.txt","-i","FMAP"],
                       capture_output=True,text=True,timeout=120)
    if r.returncode != 0 or not os.path.exists(p):
        print(f"  rc={r.returncode}, no file")
        for ln in (r.stdout+r.stderr).splitlines()[-3:]:
            print("  |",ln)
        continue
    d = open(p,"rb").read()
    z = 100*d.count(0)/max(len(d),1)
    matches = sum(1 for a,b in zip(d, stock_fmap) if a == b)
    pct = 100 * matches / len(stock_fmap)
    print(f"  read len={len(d)} zero%={z:.1f}  match-stock={pct:.1f}%  sig={d[:8]!r}")
    reads.append(d)

hold["run"] = False; time.sleep(0.5)

if len(reads) >= 2:
    print("\n[per-byte majority vote across reads]")
    L = min(len(r) for r in reads)
    voted = bytearray(L)
    for i in range(L):
        # majority value at position i across reads
        cands = [r[i] for r in reads]
        # pick most common; tie -> stock value
        from collections import Counter
        c = Counter(cands)
        voted[i] = c.most_common(1)[0][0]
    matches = sum(1 for a,b in zip(voted, stock_fmap[:L]) if a == b)
    print(f"  voted match-stock = {100*matches/L:.1f}%  sig={bytes(voted[:8])!r}")
    # Also: count bytes where ANY read matches stock (chip-is-on-bus indicator)
    any_match = 0
    for i in range(L):
        if any(r[i] == stock_fmap[i] for r in reads):
            any_match += 1
    print(f"  any-read matches stock = {100*any_match/L:.1f}%  (chip-on-bus indicator)")

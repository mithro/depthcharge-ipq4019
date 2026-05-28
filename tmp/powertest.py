#!/usr/bin/env python3
"""Monitor EC + AP consoles around a gale AP power-on; poll power state."""
import time, threading, serial

def openp(port, b):
    s = serial.Serial(); s.port = port; s.baudrate = b; s.timeout = 0.1
    s.dtr = False; s.rts = False; s.open(); return s

ec = openp("/dev/ttyUSB0", 115200)
ap = openp("/dev/ttyUSB1", 115200)

ec_log, ap_log = [], []
stop = False
def rd(ser, sink):
    while not stop:
        c = ser.read(4096)
        if c: sink.append((time.time(), c))
threading.Thread(target=rd, args=(ec, ec_log), daemon=True).start()
threading.Thread(target=rd, args=(ap, ap_log), daemon=True).start()

def ec_cmd(c):
    ec.write((c + "\r").encode()); ec.flush()

t0 = time.time()
ec_cmd("gale power off"); time.sleep(2)
print(f"[{time.time()-t0:4.1f}] sent: gale power on")
ec_cmd("gale power on")
for i in range(8):
    time.sleep(2.5)
    ec_cmd("gale power")          # poll state
print("[monitoring 25s total]")
time.sleep(3)
stop = True; time.sleep(0.3)
ec.close(); ap.close()

def dump(name, log):
    print(f"\n===== {name} console ({sum(len(c) for _,c in log)} bytes) =====")
    txt = b"".join(c for _, c in log).decode("latin1", "replace")
    for ln in txt.splitlines():
        if ln.strip():
            print(" |", ln[:150])
dump("EC", ec_log)
dump("AP", ap_log)

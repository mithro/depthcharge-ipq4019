#!/usr/bin/env python3
"""Reusable SuzyQ serial console helper.

Usage:
  con.py probe                       # identify EC vs AP on ttyUSB0/1
  con.py <port> [cmd] [--wait S]     # send cmd (\\r appended), print reply
  con.py <port> --read S             # just read for S seconds (passive)
port may be 0/1 or /dev/ttyUSBN.
"""
import sys, time, serial

def openport(port):
    # 0 = EC console (if00), 1 = AP console (if01); use stable by-id paths
    byid = {"0": "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0",
            "1": "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"}
    port = byid.get(port, port)
    s = serial.Serial()
    s.port = port; s.baudrate = 115200; s.timeout = 0.2
    s.dtr = False; s.rts = False
    s.open()
    return s

def drain(s, secs):
    buf, t0 = b"", time.time()
    while time.time() - t0 < secs:
        c = s.read(4096)
        if c: buf += c
    return buf.decode("latin1", "replace")

def send(s, cmd):
    s.reset_input_buffer()
    s.write((cmd + "\r").encode())
    s.flush()

if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "probe":
        for p in ("0", "1"):
            print(f"\n===== /dev/ttyUSB{p} =====")
            try:
                s = openport(p)
                # wake + identify
                send(s, ""); time.sleep(0.3)
                for cmd in ("version", "help", "sysinfo"):
                    send(s, cmd)
                    r = drain(s, 1.2)
                    if r.strip():
                        print(f"--- '{cmd}' ->")
                        for ln in r.splitlines()[-15:]:
                            print("  |", ln[:150])
                s.close()
            except Exception as e:
                print("  error:", e)
    elif a:
        port = a[0]
        if "--read" in a:
            secs = float(a[a.index("--read")+1])
            s = openport(port); print(drain(s, secs)); s.close()
        else:
            wait = 2.0
            if "--wait" in a:
                wait = float(a[a.index("--wait")+1]); a = a[:a.index("--wait")]
            cmd = a[1] if len(a) > 1 else ""
            s = openport(port); send(s, cmd); print(drain(s, wait)); s.close()
    else:
        print(__doc__)

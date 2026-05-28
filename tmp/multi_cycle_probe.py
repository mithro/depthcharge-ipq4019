#!/usr/bin/env python3
"""Multi-cycle probe (passive, no writes):
- Do N root-port power-cycles in sequence.
- After each cycle, IMMEDIATELY try flashrom chip-detect repeatedly for ~8s.
- In parallel, sample lsusb every 0.5s looking for Qualcomm (05c6) devices or
  any new VID:PID we haven't seen.
Reports any window where flashrom detects the chip, and any unusual USB
device that appears during bootrom hang."""
import subprocess, time, os, threading, serial
PORT = "/sys/bus/usb/devices/3-0:1.0/usb3-port1/disable"
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
FR = "/usr/sbin/flashrom"
CHIP = "W25Q64BV/W25Q64CV/W25Q64FV"
N_CYCLES = 4

def lsusb_ids():
    r = subprocess.run(["lsusb"], capture_output=True, text=True)
    ids = set()
    for ln in r.stdout.splitlines():
        # parse: Bus xxx Device yyy: ID VID:PID
        parts = ln.split()
        for i,p in enumerate(parts):
            if p == "ID" and i+1 < len(parts):
                ids.add(parts[i+1])
    return ids

def setdis(v):
    subprocess.run(["sudo","sh","-c",f"echo {v} > {PORT}"], check=True)

def present():
    return "18d1:500f" in subprocess.run(["lsusb"], capture_output=True, text=True).stdout

# Baseline USB IDs (steady state)
baseline = lsusb_ids()
print(f"[baseline USB IDs: {sorted(baseline)}]")

# Background USB watcher
new_ids = []
stop_watch = False
def watcher():
    while not stop_watch:
        cur = lsusb_ids()
        for vid in cur - baseline:
            if vid not in [x[0] for x in new_ids]:
                new_ids.append((vid, time.strftime("%H:%M:%S")))
                print(f"  [USB+] {vid} at {time.strftime('%H:%M:%S')}")
        time.sleep(0.3)
threading.Thread(target=watcher, daemon=True).start()

any_detect = False

for cycle in range(N_CYCLES):
    print(f"\n=== Cycle {cycle+1}/{N_CYCLES} ===")
    print("[cut power]"); setdis(1)
    for _ in range(10):
        time.sleep(1)
        if not present(): break
    time.sleep(3)
    print("[restore]"); setdis(0)
    # Don't wait for EC tty — start trying flashrom RDID immediately
    # and keep trying for ~10s while the device boots and hangs.
    t0 = time.time()
    attempt = 0
    while time.time() - t0 < 12:
        attempt += 1
        # short timeout flashrom — just chip detect
        r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-c", CHIP, "--flash-name"],
                           capture_output=True, text=True, timeout=15)
        out = r.stdout + r.stderr
        if r.returncode == 0 and ("Winbond" in out or "Macronix" in out):
            elapsed = time.time() - t0
            print(f"  [DETECT] attempt {attempt} at t+{elapsed:.1f}s")
            print(f"    {[l for l in out.splitlines() if 'flash chip' in l.lower() or 'name' in l.lower()][:2]}")
            any_detect = True
            break
        # Also check if we got "Found" but ambiguous
        if "Found" in out and "flash chip" in out:
            elapsed = time.time() - t0
            print(f"  [PARTIAL DETECT] attempt {attempt} at t+{elapsed:.1f}s — found a chip!")
            for ln in out.splitlines():
                if "Found" in ln: print(f"    | {ln}")
            any_detect = True
            break

stop_watch = True
time.sleep(0.4)
print(f"\n=== SUMMARY ===")
print(f"  detected this run: {any_detect}")
print(f"  new USB IDs seen (not in baseline): {new_ids}")

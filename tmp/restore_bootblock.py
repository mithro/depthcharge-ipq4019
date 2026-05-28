#!/usr/bin/env python3
"""Attempt to restore the stock 4KB bootblock at offset 0 in the narrow clean
window after a root-port power-cycle, before the IPQ bootrom starts contending.

Strategy:
- Cycle the gale via usb3-port1/disable.
- Hammer `flashrom -c CHIP --flash-name` until detection (<~10s).
- Immediately attempt `flashrom -w STOCK -l layout -i BOOTBLOCK_4K --noverify-all`.
- Repeat up to N times. After each cycle that reports a verified/no-content-changed
  result, power-cycle once more and check whether the AP now outputs coreboot
  banner on UART (= bootblock is good, IPQ booted stock-like)."""
import subprocess, time, serial, os, threading
PORT = "/sys/bus/usb/devices/3-0:1.0/usb3-port1/disable"
EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"
FR = "/usr/sbin/flashrom"
CHIP = "W25Q64BV/W25Q64CV/W25Q64FV"
STOCK = "/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin"
N_CYCLES = 6

def present():
    return "18d1:500f" in subprocess.run(["lsusb"], capture_output=True, text=True).stdout
def setdis(v):
    subprocess.run(["sudo","sh","-c",f"echo {v} > {PORT}"], check=True)
def ec(c, w=0.4):
    try:
        s=serial.Serial(); s.port=EC; s.baudrate=115200; s.timeout=0.1
        s.dtr=False; s.rts=False; s.open()
        s.write((c+"\r").encode()); s.flush(); time.sleep(w)
        s.read(8192); s.close(); return True
    except Exception:
        return False

def cycle():
    print("  [cut]"); setdis(1)
    for _ in range(10):
        time.sleep(1)
        if not present(): break
    time.sleep(3)
    print("  [restore]"); setdis(0)

def try_detect_then_write(deadline_s=10):
    """Hammer flashrom RDID. On detect, immediately attempt the 4KB write."""
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-c", CHIP, "--flash-name"],
                           capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and "Winbond" in (r.stdout + r.stderr):
            elapsed = time.time() - t0
            print(f"  [DETECT t+{elapsed:.1f}s] attempting 4KB write...")
            # Set WP_L=1 quickly via EC (best-effort; don't slow the window)
            ec("gpioset WP_L 1", w=0.2)
            w = subprocess.run(
                ["sudo", FR, "-p", "raiden_debug_spi", "-c", CHIP,
                 "-w", STOCK, "-l", "tmp/layout.txt", "-i", "BOOTBLOCK_4K",
                 "--noverify-all"],
                capture_output=True, text=True, timeout=60)
            out = w.stdout + w.stderr
            print(f"  [WRITE rc={w.returncode}]")
            for ln in out.splitlines()[-10:]:
                print("   |", ln)
            verified = "VERIFIED" in out or "Erase/write done" in out or "VERIFIED" in out
            return w.returncode, out
    print(f"  [no detect in {deadline_s}s]")
    return None, ""

# AP UART monitor — accumulates output across cycles
ap_buf = []; ap_stop = False
def ap_reader():
    while not ap_stop:
        try:
            s=serial.Serial(); s.port=AP; s.baudrate=115200; s.timeout=0.1
            s.dtr=False; s.rts=False; s.open()
            while not ap_stop:
                d=s.read(4096)
                if d: ap_buf.append((time.time(), d))
            s.close()
        except Exception:
            time.sleep(0.3)
threading.Thread(target=ap_reader, daemon=True).start()

for k in range(N_CYCLES):
    print(f"\n=== Write Cycle {k+1}/{N_CYCLES} ===")
    cycle()
    rc, out = try_detect_then_write(deadline_s=12)

# Final test: power-cycle one more time + observe whether AP now boots
print(f"\n=== Final boot test ===")
ap_buf.clear()
cycle()
print("  [observe AP UART 12s]")
time.sleep(12)
ap_stop = True; time.sleep(0.3)

merged = b"".join(b for _,b in ap_buf)
text = merged.decode("latin1","replace")
nonempty = [l for l in text.splitlines() if l.strip()]
print(f"  AP non-empty lines after final cycle: {len(nonempty)}")
for l in nonempty[:20]:
    print("  >",l[:140])
banner_seen = "coreboot" in text.lower() or "depthcharge" in text.lower() or "starting" in text.lower()
print(f"  banner_seen: {banner_seen}")

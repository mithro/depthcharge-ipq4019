#!/usr/bin/env python3
"""Flash GBB + VBLOCK_A + VBLOCK_B from the resigned image via SuzyQ.

Procedure:
  1. UCSI hard-cycle to clean state.
  2. Boot to stock recovery loop (gale rec on, dev off, gale power on).
  3. Wait for recovery loop to be running (confirms RO depthcharge is yielding the bus).
  4. gale power off — EC keeps the raiden bridge's VDD_3P3 alive for our writes.
  5. gpioset WP_L 1 — deassert write-protect so the GBB sector in WP_RO is writable.
  6. flashrom -w resigned.bin --fmap -i GBB -i VBLOCK_A -i VBLOCK_B  (single call).
  7. Verify pass.

The three target regions cover all 5 differing sectors between the current chip
and the resigned image (verified by sector-level diff: 20 KB, no other changes)."""
import subprocess, time, os, serial, threading, sys

REPO = "/home/tim/local/gwifi/depthcharge-ipq4019"
EC   = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP   = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"
FR   = "/usr/sbin/flashrom"
CHIP = "W25Q64BV/W25Q64CV/W25Q64FV"
IMG  = f"{REPO}/tmp/gale-netboot-resigned.bin"

def lsusb_has(vp):
    return vp in subprocess.run(["lsusb"], capture_output=True, text=True).stdout

def ec(cmd, w=0.4):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.15
    s.dtr = False; s.rts = False; s.open()
    s.write((cmd + "\r").encode()); s.flush(); time.sleep(w)
    r = s.read(8192); s.close()
    return r.decode("latin1", "replace")

def ucsi_cycle():
    print("[UCSI CONNECTOR_RESET]")
    subprocess.run(["sudo", "sh", "-c",
        "echo 0x10003 > /sys/kernel/debug/usb/ucsi/USBC000:00/command"], check=True)
    for _ in range(40):
        if lsusb_has("18d1:500f"): break
        time.sleep(0.05)
    for _ in range(30):
        if os.path.exists(EC): break
        time.sleep(0.1)
    time.sleep(0.5)

def wait_for_recovery_loop(timeout=30):
    """Read AP UART until we see VbBootRecovery's wait-loop lines, confirming
    stock RO depthcharge is running and releasing the SPI bus periodically."""
    buf = []; stop = [False]
    def reader():
        while not stop[0]:
            try:
                s = serial.Serial(); s.port = AP; s.baudrate = 115200; s.timeout = 0.05
                s.dtr = False; s.rts = False; s.open()
                while not stop[0]:
                    d = s.read(4096)
                    if d: buf.append(d)
                s.close()
            except Exception:
                time.sleep(0.2)
    t = threading.Thread(target=reader, daemon=True); t.start()
    time.sleep(0.2)
    t0 = time.time()
    while time.time() - t0 < timeout:
        text = b"".join(buf).decode("latin1", "replace")
        if "VbBootRecovery() attempting to load kernel" in text:
            stop[0] = True; time.sleep(0.2)
            return True, text
        time.sleep(0.5)
    stop[0] = True; time.sleep(0.2)
    return False, b"".join(buf).decode("latin1", "replace")

# --- main ---
ucsi_cycle()

print("[gale rec on, dev off, power on  -> stock recovery loop]")
ec("gale rec on"); ec("gale dev off"); ec("gale power on")

print("[waiting for recovery loop on AP UART...]")
ok, _ = wait_for_recovery_loop(timeout=30)
if not ok:
    print("ERROR: recovery loop never appeared on AP UART"); sys.exit(1)
print("  recovery loop confirmed; AP is yielding the SPI bus")

# Force WP_L=1 NOW, while EC rails are alive (override persists across power off).
print("[gpioset WP_L 1  — set BEFORE gale power off]")
ec("gpioset WP_L 1", w=0.3)
gp_pre = ec("gpioget", w=0.6)
wp_pre = next((l.strip() for l in gp_pre.splitlines() if "WP_L" in l), None)
print(f"  pre-poweroff WP_L: {wp_pre}")
if not wp_pre or "*" not in wp_pre:
    print("  ERROR: gpioset WP_L 1 didn't take (no * override marker); aborting")
    sys.exit(4)

# Atomic window: gale power off via the SAME ec() function flash_rw.py uses
# (which reads the EC response — drains the EC's output buffer; the absence
# of this drain in earlier attempts may have left the EC task blocked on
# serial output and not servicing the raiden bridge properly).
print("[gale power off  (using ec() exactly like flash_rw.py)]")
print("  ec output:", ec("gale power off", w=1.2).strip()[-60:])

# Single atomic write of all 3 regions.
print(f"  flashrom -w resigned.bin --fmap -i GBB -i VBLOCK_A -i VBLOCK_B")
t0 = time.time()
r = subprocess.run(["sudo", FR, "-p", "raiden_debug_spi", "-c", CHIP,
                    "-w", IMG, "--fmap",
                    "-i", "GBB", "-i", "VBLOCK_A", "-i", "VBLOCK_B"],
                   capture_output=True, text=True, timeout=600)
elapsed = time.time() - t0
print(f"  rc={r.returncode}  elapsed={elapsed:.1f}s")
for ln in (r.stdout + r.stderr).splitlines()[-12:]:
    print(f"  | {ln}")
verified = r.returncode == 0 and "VERIFIED" in (r.stdout + r.stderr)
print()
print(f"RESULT: {'VERIFIED' if verified else 'FAILED'}")
sys.exit(0 if verified else 3)

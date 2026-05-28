#!/usr/bin/env python3
"""Software-controlled hard power cycle of the gale via UCSI CONNECTOR_RESET.

The gale's whole stack (SuzyQ EC + IPQ4019 + ethernet adapters) is powered
through a USB-C hub on the laptop's port0 (controllers 0000:00:0d.0 and
0000:00:14.0). uhubctl reports the laptop's xHCI root hubs as "nops" (no
per-port power switching) and the hub as "ganged" (single global switch),
so neither sysfs port-disable nor uhubctl can cut VBUS.

UCSI (USB Type-C Connector System Software Interface) over ACPI exposes a
debugfs interface that DOES allow triggering a connector reset via the PD
controller. CONNECTOR_RESET on connector 1 (= port0) drops VBUS, the hub
loses power, the gale fully resets. ~1.25 seconds end-to-end.

This is the software equivalent of unplugging the USB-C cable from the laptop.

Usage:  uv run --no-project python tmp/ucsi_hardcycle.py [--wait-back SECONDS]
"""
import subprocess, time, sys, os
PORT0_CMD = "/sys/kernel/debug/usb/ucsi/USBC000:00/command"
# CONNECTOR_RESET = 0x03 | (connector_num << 16); port0 = connector 1.
RESET_CMD = "0x10003"

def lsusb_has(vp):
    return vp in subprocess.run(["lsusb"], capture_output=True, text=True).stdout

def hardcycle(wait_back=5.0):
    """Trigger UCSI CONNECTOR_RESET on the gale's USB-C port; wait for
    re-enumeration. Returns time-to-return in seconds, or None on timeout."""
    if not lsusb_has("18d1:500f"):
        print("warning: gale (18d1:500f) not currently present before cycle")
    subprocess.run(["sudo", "sh", "-c", f"echo {RESET_CMD} > {PORT0_CMD}"], check=True)
    # USB drops within ~0.1s
    t0 = time.time()
    while time.time() - t0 < 3:
        if not lsusb_has("18d1:500f"): break
        time.sleep(0.05)
    drop_t = time.time() - t0
    # Wait for return
    while time.time() - t0 < wait_back:
        if lsusb_has("18d1:500f"):
            return_t = time.time() - t0
            return (drop_t, return_t)
        time.sleep(0.1)
    return (drop_t, None)

if __name__ == "__main__":
    wait = float(sys.argv[sys.argv.index("--wait-back")+1]) if "--wait-back" in sys.argv else 5.0
    drop_t, return_t = hardcycle(wait_back=wait)
    print(f"USB drop at t+{drop_t:.2f}s")
    if return_t:
        print(f"USB back at  t+{return_t:.2f}s")
    else:
        print(f"USB did NOT return within {wait}s — gale may need manual replug")

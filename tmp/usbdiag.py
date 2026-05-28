#!/usr/bin/env python3
import subprocess as sp, os, re, glob

def out(args):
    r = sp.run(args, capture_output=True, text=True)
    return r.stdout + r.stderr

print("=== lsusb (Google/18d1) ===")
ls = out(["lsusb"])
gline = [l for l in ls.splitlines() if "18d1" in l.lower() or "google" in l.lower()]
print("\n".join(gline) or "(none)")
gid = None
for l in gline:
    m = re.search(r"ID ([0-9a-fA-F]{4}:[0-9a-fA-F]{4})", l)
    if m:
        gid = m.group(1); break
print("device id:", gid)

if gid:
    v = out(["lsusb", "-v", "-d", gid])
    keys = ("bNumInterfaces", "bInterfaceNumber", "bInterfaceClass",
            "iInterface", "bNumEndpoints", "bEndpointAddress",
            "idVendor", "idProduct", "bInterfaceProtocol", "bInterfaceSubClass")
    for ln in v.splitlines():
        s = ln.strip()
        if any(k in s for k in keys):
            print("  ", s)

print("=== kernel drivers bound to 18d1 interfaces ===")
for dev in glob.glob("/sys/bus/usb/devices/*/idVendor"):
    try:
        if open(dev).read().strip() == "18d1":
            base = os.path.dirname(dev)
            prod = open(os.path.join(base, "idProduct")).read().strip()
            print(f" device {os.path.basename(base)} 18d1:{prod}")
            for intf in sorted(glob.glob(base + "/*:*")):
                drv = os.path.join(intf, "driver")
                d = os.path.basename(os.readlink(drv)) if os.path.islink(drv) else "(none)"
                cls = ""
                ic = os.path.join(intf, "bInterfaceClass")
                if os.path.exists(ic):
                    cls = open(ic).read().strip()
                print(f"   {os.path.basename(intf):20s} class={cls} driver={d}")
    except Exception as e:
        print("  err", e)

print("=== DHCP leases (shared net on enx00e04c360636) ===")
lf = "/var/lib/NetworkManager/dnsmasq-enx00e04c360636.leases"
print(out(["cat", lf]) if os.path.exists(lf) else "(no lease file)")
print("=== ARP neighbours on gale ports ===")
print(out(["ip", "neigh", "show", "dev", "enx00e04c360636"]))
print(out(["ip", "neigh", "show", "dev", "enx00e04c68016b"]))

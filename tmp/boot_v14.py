#!/usr/bin/env python3
"""UCSI cycle, boot v14, capture for 180s. Aggressive filtering: only print lines
matching driver progress / link / DHCP / TFTP / kernel handoff."""
import subprocess, time, os, serial, threading

EC = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"

def ec(c, w=0.4):
    s = serial.Serial(); s.port = EC; s.baudrate = 115200; s.timeout = 0.15
    s.dtr = False; s.rts = False; s.open()
    s.write((c + "\r").encode()); s.flush(); time.sleep(w)
    s.read(8192); s.close()

# UCSI cycle
subprocess.run(["sudo", "sh", "-c",
    "echo 0x10003 > /sys/kernel/debug/usb/ucsi/USBC000:00/command"], check=True)
time.sleep(0.3)
while subprocess.run(["lsusb", "-d", "18d1:500f"],
                     capture_output=True, text=True).stdout:
    time.sleep(0.1)
for _ in range(100):
    if subprocess.run(["lsusb", "-d", "18d1:500f"],
                      capture_output=True, text=True).stdout:
        break
    time.sleep(0.1)
for _ in range(60):
    if os.path.exists(EC): break
    time.sleep(0.1)
time.sleep(2.0)

# Re-add netboot IP (UCSI cycle drops it) and restart dnsmasq
# (dnsmasq loses its socket bind when the interface goes down)
subprocess.run(["sudo","ip","addr","add","10.42.1.1/24","dev","enx00e04c68016b"],
               capture_output=True)
subprocess.run(["sudo","ip","link","set","enx00e04c68016b","up"], capture_output=True)
subprocess.run(["uv","run","--no-project","python","tmp/netboot_server.py",
                "start","openwrt-gale.itb"], capture_output=True, timeout=15)

# Start tcpdump in background to capture any DHCP/ARP traffic
tcpdump_log = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/tcpdump-v14.log"
open(tcpdump_log, "w").close()  # truncate
tcpdump_proc = subprocess.Popen(
    ["sudo", "tcpdump", "-l", "-nn", "-e", "-i", "enx00e04c68016b",
     "-w", tcpdump_log.replace(".log", ".pcap"),
     "(port 67 or port 68 or port 69) or arp or icmp"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)

ap_buf = []; stop = False
def reader():
    while not stop:
        try:
            s = serial.Serial(); s.port = AP; s.baudrate = 115200; s.timeout = 0.05
            s.dtr = False; s.rts = False; s.open()
            while not stop:
                d = s.read(4096)
                if d: ap_buf.append(d)
            s.close()
        except Exception:
            time.sleep(0.2)
threading.Thread(target=reader, daemon=True).start()
time.sleep(0.4)

ec("gale dev off"); ec("gale rec off"); ec("gale power on")
print("[capture 180s]")
t0 = time.time()
while time.time() - t0 < 180:
    text = b"".join(ap_buf).decode("latin1", "replace")
    if "giving up" in text or "Data Abort" in text or "Starting kernel" in text:
        time.sleep(3); break
    time.sleep(0.5)

stop = True; time.sleep(0.5)
subprocess.run(["sudo","kill",str(tcpdump_proc.pid)], capture_output=True)
time.sleep(0.5)
text = b"".join(ap_buf).decode("latin1", "replace")
lines = [l for l in text.splitlines() if l.strip()]

print(f"\n=== AP UART {len(lines)} lines ===")
# Filter out the calibration spam and bootblock noise
for l in lines:
    if any(k in l for k in ("ipq4019", "PSGMII", "self-test", "Waiting", "link", "DHCP",
                            "Tftp", "Bootfile", "Starting kernel", "Data Abort", "ERROR",
                            "FAIL", "fallback", "Starting netboot", "uIP", "got reply",
                            "My ip", "openwrt-gale")):
        if "try " not in l or "result 1" in l:  # skip "try N serial result 0" spam
            print(f"  | {l[:200]}")

# Also dump last 20 lines for context
print("\n=== LAST 30 LINES ===")
for l in lines[-30:]:
    print(f"  > {l[:200]}")

# DHCP lease check
print("\n=== DHCP leases ===")
try:
    print(open("/home/tim/local/gwifi/depthcharge-ipq4019/tmp/dnsmasq-netboot.leases").read())
except Exception as e:
    print(f"  no leases file: {e}")

# dnsmasq log tail
print("\n=== dnsmasq log (last 15) ===")
r = subprocess.run(["sudo","tail","-15","/home/tim/local/gwifi/depthcharge-ipq4019/tmp/dnsmasq-netboot.log"],
                   capture_output=True, text=True)
print(r.stdout + r.stderr)

# tcpdump readout
print("\n=== tcpdump captured packets ===")
pcap = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/tcpdump-v14.pcap"
r = subprocess.run(["sudo","tcpdump","-r",pcap,"-nn","-e","-c","50"],
                   capture_output=True, text=True)
print(r.stdout + r.stderr)

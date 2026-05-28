#!/usr/bin/env python3
"""Stand up a DHCP+TFTP server for depthcharge netboot on the free gale NIC.
Also leaves the NM 'Share Internet' dnsmasq on enx00e04c360636 (10.42.0.1) alone.

start:   configure enx00e04c68016b = 10.42.1.1/24, run dnsmasq (DHCP+TFTP)
stop:    kill our dnsmasq, flush the iface
"""
import subprocess, sys, os, signal

IFACE = "enx00e04c68016b"          # 1000M gale port, currently no IP
IP = "10.42.1.1"
TFTPROOT = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/tftproot"
PIDFILE = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/dnsmasq-netboot.pid"
LEASES = "/home/tim/local/gwifi/depthcharge-ipq4019/tmp/dnsmasq-netboot.leases"

def sh(args):
    print("  $", " ".join(args))
    r = subprocess.run(args, capture_output=True, text=True)
    if r.stdout.strip(): print("   ", r.stdout.strip())
    if r.stderr.strip(): print("   ", r.stderr.strip())
    return r.returncode

def start(bootfile):
    os.makedirs(TFTPROOT, exist_ok=True)
    sh(["sudo", "ip", "addr", "flush", "dev", IFACE])
    sh(["sudo", "ip", "addr", "add", f"{IP}/24", "dev", IFACE])
    sh(["sudo", "ip", "link", "set", IFACE, "up"])
    # kill any stale instance
    if os.path.exists(PIDFILE):
        sh(["sudo", "pkill", "-F", PIDFILE]) if False else None
    args = ["sudo", "dnsmasq",
            "--no-daemon" if False else "--keep-in-foreground",
            "--conf-file=/dev/null", "--no-hosts", "--bind-interfaces",
            f"--interface={IFACE}", "--except-interface=lo",
            f"--listen-address={IP}",
            "--dhcp-range=10.42.1.50,10.42.1.150,5m",
            f"--dhcp-leasefile={LEASES}",
            f"--dhcp-boot={bootfile}",
            "--enable-tftp", f"--tftp-root={TFTPROOT}",
            f"--pid-file={PIDFILE}",
            "--log-dhcp", "--log-queries"]
    print("dnsmasq DHCP+TFTP on", IFACE, IP, "tftproot", TFTPROOT, "bootfile", bootfile)
    print("  (run this in background:)")
    print("   sudo", " ".join(a for a in args[1:]))

if __name__ == "__main__":
    bf = sys.argv[2] if len(sys.argv) > 2 else "vmlinux.fit"
    if len(sys.argv) > 1 and sys.argv[1] == "start":
        start(bf)
    else:
        print(__doc__)

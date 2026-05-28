#!/usr/bin/env python3
"""Stand up a DHCP+TFTP server for depthcharge netboot on the free gale NIC.
Also leaves the NM 'Share Internet' dnsmasq on enx00e04c360636 (10.42.0.1) alone.

  python netboot_server.py start [bootfile]    # default bootfile = openwrt-gale.itb
  python netboot_server.py stop                # kill our dnsmasq + flush iface
  python netboot_server.py status              # show pid + leases + last log lines
"""
import subprocess, sys, os, time

IFACE = "enx00e04c68016b"          # 1000M gale port, currently no IP
IP = "10.42.1.1"
ROOT = "/home/tim/local/gwifi/depthcharge-ipq4019"
TFTPROOT = f"{ROOT}/tmp/tftproot"
PIDFILE = f"{ROOT}/tmp/dnsmasq-netboot.pid"
LEASES = f"{ROOT}/tmp/dnsmasq-netboot.leases"
LOGFILE = f"{ROOT}/tmp/dnsmasq-netboot.log"

def sh(args, quiet=False):
    if not quiet:
        print("  $", " ".join(args))
    r = subprocess.run(args, capture_output=True, text=True)
    if not quiet:
        if r.stdout.strip(): print("   ", r.stdout.strip())
        if r.stderr.strip(): print("   ", r.stderr.strip())
    return r.returncode

def stop():
    if os.path.exists(PIDFILE):
        try:
            pid = open(PIDFILE).read().strip()
            print(f"  killing dnsmasq pid={pid}")
            sh(["sudo", "kill", pid])
            time.sleep(0.5)
        except Exception as e:
            print(f"  kill error: {e}")
        try: os.unlink(PIDFILE)
        except: pass
    sh(["sudo", "ip", "addr", "flush", "dev", IFACE])

def start(bootfile):
    if not os.path.exists(os.path.join(TFTPROOT, bootfile)):
        print(f"  ERROR: {TFTPROOT}/{bootfile} does not exist"); sys.exit(1)
    os.makedirs(TFTPROOT, exist_ok=True)
    # If a stale instance is running, stop it first
    stop()
    sh(["sudo", "ip", "addr", "add", f"{IP}/24", "dev", IFACE])
    sh(["sudo", "ip", "link", "set", IFACE, "up"])
    args = ["sudo", "dnsmasq",
            "--conf-file=/dev/null", "--no-hosts",
            "--bind-interfaces",
            # IMPORTANT: don't drop privileges — default user 'nobody'
            # cannot read /home/tim/..., so TFTP requests would silently
            # time out. Verified by tmp/test_netboot_server.py loopback test.
            "--user=root",
            f"--interface={IFACE}", "--except-interface=lo",
            f"--listen-address={IP}",
            "--dhcp-range=10.42.1.50,10.42.1.150,5m",
            f"--dhcp-leasefile={LEASES}",
            f"--dhcp-boot={bootfile}",
            "--enable-tftp", f"--tftp-root={TFTPROOT}",
            f"--pid-file={PIDFILE}",
            f"--log-facility={LOGFILE}",
            "--log-dhcp", "--log-queries"]
    print(f"\nstarting dnsmasq: DHCP+TFTP on {IFACE} {IP}, bootfile={bootfile}")
    r = subprocess.run(args, capture_output=True, text=True, timeout=10)
    if r.stdout.strip(): print("  stdout:", r.stdout.strip())
    if r.stderr.strip(): print("  stderr:", r.stderr.strip())
    time.sleep(0.5)
    if os.path.exists(PIDFILE):
        pid = open(PIDFILE).read().strip()
        print(f"\n  ✓ running (pid={pid})  log: tail -F {LOGFILE}")
        print(f"  leases:                  tail -F {LEASES}")
    else:
        print(f"\n  ✗ FAILED to start (rc={r.returncode})"); sys.exit(1)

def status():
    if os.path.exists(PIDFILE):
        pid = open(PIDFILE).read().strip()
        print(f"  dnsmasq pid: {pid}")
    else:
        print(f"  dnsmasq NOT running (no pidfile)")
    if os.path.exists(LEASES):
        print(f"  leases ({LEASES}):")
        for ln in open(LEASES).readlines():
            print(f"    {ln.rstrip()}")
    if os.path.exists(LOGFILE):
        print(f"  last 10 log lines ({LOGFILE}):")
        lines = open(LOGFILE).readlines()
        for ln in lines[-10:]:
            print(f"    {ln.rstrip()}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "start":
        bf = sys.argv[2] if len(sys.argv) > 2 else "openwrt-gale.itb"
        start(bf)
    elif cmd == "stop":
        stop()
    elif cmd == "status":
        status()
    else:
        print(__doc__)

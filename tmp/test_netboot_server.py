#!/usr/bin/env python3
"""End-to-end test of the netboot server on loopback (no gale needed):
  1. Start dnsmasq on 127.0.0.1 with the real DHCP+TFTP config.
  2. Use curl to TFTP-fetch openwrt-gale.itb from 127.0.0.1.
  3. Verify byte-for-byte equality with the source file.
  4. Stop dnsmasq, clean up.

Validates that the server side is correct independent of the gale,
so when the device is recovered there is no DHCP/TFTP config bug to
debug on top of the driver bring-up."""
import subprocess, os, time, hashlib, signal, sys

ROOT = "/home/tim/local/gwifi/depthcharge-ipq4019"
TFTPROOT = f"{ROOT}/tmp/tftproot"
BOOTFILE = "openwrt-gale.itb"
SRC = f"{TFTPROOT}/{BOOTFILE}"
PIDFILE = f"{ROOT}/tmp/dnsmasq-test.pid"
LEASES = f"{ROOT}/tmp/dnsmasq-test.leases"
LOGFILE = f"{ROOT}/tmp/dnsmasq-test.log"
DEST = f"{ROOT}/tmp/test-tftp-out.bin"

def cleanup():
    if os.path.exists(PIDFILE):
        subprocess.run(["sudo", "pkill", "-F", PIDFILE], capture_output=True)
        time.sleep(0.5)
        if os.path.exists(PIDFILE):
            os.unlink(PIDFILE)
    for f in (LEASES, LOGFILE, DEST):
        if os.path.exists(f):
            try: os.unlink(f)
            except: pass

cleanup()

print(f"[step 1] verify source file: {SRC}")
size = os.path.getsize(SRC)
src_sha = hashlib.sha256(open(SRC,"rb").read()).hexdigest()
print(f"  size={size}  sha256={src_sha}")
assert size == 8338516, f"unexpected source size {size}"

print(f"\n[step 2] start dnsmasq on 127.0.0.1 (DHCP+TFTP)")
args = ["sudo", "dnsmasq",
        "--conf-file=/dev/null", "--no-hosts",
        # Do NOT drop privileges — default user 'nobody' cannot read
        # /home/tim/... TFTP would silently time out.
        "--user=root",
        "--bind-interfaces",
        "--listen-address=127.0.0.1",
        "--interface=lo",
        "--except-interface=enx00e04c68016b",
        "--except-interface=enx00e04c360636",
        # tiny test DHCP scope on lo (won't conflict)
        "--dhcp-range=127.255.255.100,127.255.255.150,5m",
        f"--dhcp-leasefile={LEASES}",
        f"--dhcp-boot={BOOTFILE}",
        "--enable-tftp", f"--tftp-root={TFTPROOT}",
        f"--pid-file={PIDFILE}",
        "--log-facility=" + LOGFILE,
        "--log-dhcp", "--log-queries"]
print("  starting...")
r = subprocess.run(args, capture_output=True, text=True, timeout=10)
print(f"  rc={r.returncode}")
if r.stdout.strip(): print("  stdout:", r.stdout.strip())
if r.stderr.strip(): print("  stderr:", r.stderr.strip())
time.sleep(0.5)
if not os.path.exists(PIDFILE):
    print("  FAILED: no pidfile written"); sys.exit(1)
with open(PIDFILE) as f: pid = f.read().strip()
print(f"  dnsmasq pid={pid}")

print(f"\n[step 3] tftp-fetch {BOOTFILE} via curl from 127.0.0.1")
t0 = time.time()
r = subprocess.run(["curl", "-s", "-S", "--max-time", "60",
                    f"tftp://127.0.0.1/{BOOTFILE}",
                    "-o", DEST],
                   capture_output=True, text=True, timeout=70)
elapsed = time.time() - t0
print(f"  curl rc={r.returncode}  elapsed={elapsed:.1f}s")
if r.stderr.strip(): print("  curl stderr:", r.stderr.strip())

ok = False
if r.returncode == 0 and os.path.exists(DEST):
    got_size = os.path.getsize(DEST)
    got_sha = hashlib.sha256(open(DEST,"rb").read()).hexdigest()
    print(f"  fetched: size={got_size}  sha256={got_sha}")
    if got_size == size and got_sha == src_sha:
        print("  ✓ byte-exact match")
        ok = True
    else:
        print("  ✗ MISMATCH — server is corrupting the file or short-reading")

print(f"\n[step 4] stop dnsmasq + cleanup")
cleanup()
print(f"\n=== RESULT: {'PASS' if ok else 'FAIL'} ===")
sys.exit(0 if ok else 1)

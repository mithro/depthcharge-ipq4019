#!/usr/bin/env python3
"""Full flash sequence via direct USB:
  1. Enable raiden bridge
  2. Read SR + JEDEC ID for diagnostics
  3. Erase sector at 0x550000 (4 KB sector)
  4. Verify erase (read back, should be 0xff)
  5. Page-program our 64-byte blob
  6. Verify program (read back, should match)
  7. Disable bridge
"""
import sys, time, struct
import usb.core, usb.util

VID = 0x18D1
SUBCLASS = 0x51
PROTOCOL = 0x01
REQ_ENABLE  = 0x0000
REQ_DISABLE = 0x0001
BMRT_VENDOR_OUT_INTF = 0x41

OPC_WREN  = 0x06
OPC_RDSR  = 0x05
OPC_WRSR  = 0x01
OPC_RDID  = 0x9F
OPC_SECTOR_ERASE = 0x20    # 4 KB sector erase
OPC_PAGE_PROGRAM = 0x02
OPC_READ  = 0x03

# Same SHARED_DATA blob we want to write
KERNEL_ARGS = b"root=/dev/mmcblk0p2 rootfstype=squashfs ro\x00"
def build_blob():
    blob = bytearray()
    blob += b"netboot\x00"                              # 8 bytes
    blob += struct.pack("<I", 1)                        # count = 1
    blob += struct.pack("<I", 2)                        # type = KernelArgs
    blob += struct.pack("<I", len(KERNEL_ARGS))         # size
    pad = (-len(KERNEL_ARGS)) & 3
    blob += KERNEL_ARGS + b"\x00" * pad                 # padded
    return bytes(blob)

TARGET_ADDR = 0x550000


def find_dev():
    for dev in usb.core.find(idVendor=VID, find_all=True):
        for cfg in dev:
            for intf in cfg:
                if (intf.bInterfaceClass == 0xff and
                    intf.bInterfaceSubClass == SUBCLASS and
                    intf.bInterfaceProtocol == PROTOCOL):
                    return dev, intf
    return None, None


def claim_dev():
    dev, intf = find_dev()
    if not dev:
        sys.exit("no raiden interface found")
    print(f"device 0x{dev.idVendor:04x}:0x{dev.idProduct:04x} intf {intf.bInterfaceNumber}")
    if dev.is_kernel_driver_active(intf.bInterfaceNumber):
        try: dev.detach_kernel_driver(intf.bInterfaceNumber)
        except Exception: pass
    usb.util.claim_interface(dev, intf.bInterfaceNumber)
    ep_in = ep_out = None
    for ep in intf:
        if usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK:
            if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN:
                ep_in = ep
            else:
                ep_out = ep
    return dev, intf, ep_in, ep_out


def enable_bridge(dev, intf):
    for attempt in range(8):
        try:
            dev.ctrl_transfer(BMRT_VENDOR_OUT_INTF, REQ_ENABLE,
                              0, intf.bInterfaceNumber, 0, timeout=1000)
            print(f"  bridge enabled (attempt {attempt+1})")
            return
        except usb.core.USBError as e:
            print(f"  enable attempt {attempt+1} err: {e}")
            try:
                dev.ctrl_transfer(BMRT_VENDOR_OUT_INTF, REQ_DISABLE,
                                  0, intf.bInterfaceNumber, 0, timeout=500)
            except Exception: pass
            time.sleep(0.3)
    sys.exit("cannot enable bridge")


def disable_bridge(dev, intf):
    for _ in range(3):
        try:
            dev.ctrl_transfer(BMRT_VENDOR_OUT_INTF, REQ_DISABLE,
                              0, intf.bInterfaceNumber, 0, timeout=500)
            return
        except Exception: pass


def main():
    dev, intf, ep_in, ep_out = claim_dev()
    enable_bridge(dev, intf)

    def spi(write_bytes, read_count, timeout=2000):
        write_count = len(write_bytes)
        if write_count > 62: raise ValueError("too many write bytes")
        if read_count > 62: raise ValueError("too many read bytes")
        pkt = bytes([write_count, read_count]) + write_bytes
        ep_out.write(pkt, timeout=timeout)
        rx = bytes(ep_in.read(read_count + 2, timeout=timeout))
        status = rx[0] | (rx[1] << 8)
        if status != 0:
            raise RuntimeError(f"spi command status=0x{status:04x}")
        return rx[2:2 + read_count]

    def wait_ready(timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            sr = spi(bytes([OPC_RDSR]), 1)[0]
            if not (sr & 0x01):
                return sr
            time.sleep(0.005)
        raise RuntimeError("chip stuck busy")

    try:
        # Reset sequence (0x66 + 0x99) to ensure chip is in known state.
        try:
            spi(bytes([0x66]), 0)  # enable reset
            spi(bytes([0x99]), 0)  # reset
            time.sleep(0.001)
            print("  reset sequence sent")
        except Exception as e:
            print(f"  reset err: {e}")

        # Diagnostics
        jedec = spi(bytes([OPC_RDID]), 3)
        sr = spi(bytes([OPC_RDSR]), 1)[0]
        # Try reading JEDEC ID with various dummy bytes
        for dummy in (0, 1, 2):
            try:
                jid = spi(bytes([OPC_RDID]) + b"\x00" * dummy, 3 + dummy)
                print(f"  JEDEC (after {dummy} dummies): {jid.hex()}")
            except Exception: pass
        print(f"  JEDEC ID: {jedec.hex()}")
        print(f"  SR: 0x{sr:02x}")

        # Try reads at several known-good locations + different opcodes
        for label, addr, op in [
            ("READ  @ 0x000000 (coreboot bootblock)", 0x000000, 0x03),
            ("FAST  @ 0x000000", 0x000000, 0x0B),
            ("READ  @ 0x550000", 0x550000, 0x03),
            ("FAST  @ 0x550000", 0x550000, 0x0B),
        ]:
            addr_b = bytes([(addr >> 16) & 0xff, (addr >> 8) & 0xff, addr & 0xff])
            try:
                if op == 0x0B:  # fast read needs 1 dummy byte
                    data = spi(bytes([op]) + addr_b + b"\x00", 32)
                else:
                    data = spi(bytes([op]) + addr_b, 32)
                print(f"  {label}: {data.hex()}")
            except Exception as e:
                print(f"  {label}: err {e}")

        addr_bytes = bytes([(TARGET_ADDR >> 16) & 0xff,
                            (TARGET_ADDR >>  8) & 0xff,
                             TARGET_ADDR        & 0xff])
        before = spi(bytes([OPC_READ]) + addr_bytes, 32)
        print(f"  before @ 0x{TARGET_ADDR:06x}: {before.hex()}")

        # Erase sector
        spi(bytes([OPC_WREN]), 0)
        spi(bytes([OPC_SECTOR_ERASE]) + addr_bytes, 0)
        sr = wait_ready()
        print(f"  after erase: SR=0x{sr:02x}")

        # Read after erase
        after_erase = spi(bytes([OPC_READ]) + addr_bytes, 32)
        print(f"  after erase @ 0x{TARGET_ADDR:06x}: {after_erase.hex()}")
        if not all(b == 0xff for b in after_erase):
            print("  !! erase did not clear bytes to 0xff")

        # Program our blob (max 56 bytes per packet due to 62-byte limit minus opcode+addr)
        blob = build_blob()
        print(f"  blob: {len(blob)} bytes")
        OFF = 0
        while OFF < len(blob):
            chunk = blob[OFF:OFF + 56]  # 56-byte chunks
            spi(bytes([OPC_WREN]), 0)
            addr = TARGET_ADDR + OFF
            cmd = bytes([OPC_PAGE_PROGRAM,
                         (addr >> 16) & 0xff,
                         (addr >>  8) & 0xff,
                          addr        & 0xff]) + chunk
            spi(cmd, 0)
            sr = wait_ready()
            OFF += len(chunk)
        print(f"  programmed {OFF} bytes")

        # Verify
        after_pgm = spi(bytes([OPC_READ]) + addr_bytes, len(blob))
        print(f"  after  pgm @ 0x{TARGET_ADDR:06x}: {after_pgm.hex()}")
        if after_pgm == blob:
            print("  ✓ verify PASS")
        else:
            print("  !! verify mismatch:")
            print(f"     want: {blob.hex()}")
            print(f"     got : {after_pgm.hex()}")
            sys.exit(1)

    finally:
        disable_bridge(dev, intf)
        try:
            usb.util.release_interface(dev, intf.bInterfaceNumber)
        except Exception:
            pass


if __name__ == "__main__":
    main()

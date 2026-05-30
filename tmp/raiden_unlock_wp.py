#!/usr/bin/env python3
"""Directly talk to gale's SuzyQ SPI bridge to clear the W25Q64 status
register, removing the BP/SRP block protection bits that are blocking
flashrom writes.

Protocol (from flashrom-cros raiden_debug_spi.c):
    VID 0x18D1, interface with bSubClass=0x51 + bProtocol=0x01
    Enable: control transfer bRequest=0x0000, OUT, VENDOR, INTERFACE
    Disable: bRequest=0x0001, same
    Send SPI: bulk OUT to bulk endpoint, format:
        byte[0] = write_count
        byte[1] = read_count
        bytes[2..] = SPI command bytes to send
    Receive: bulk IN, format:
        byte[0]/byte[1] = status (write_count low / high)
        bytes[2..] = read data

We'll send:
    WREN  (0x06)        — set Write Enable Latch
    WRSR  (0x01, 0x00)  — write Status Register with all-zero protect bits
Then read SR back and confirm BP bits cleared.
"""
import sys, time
import usb.core, usb.util

VID = 0x18D1
SUBCLASS = 0x51
PROTOCOL = 0x01

REQ_ENABLE  = 0x0000
REQ_DISABLE = 0x0001

LIBUSB_VENDOR_INTERFACE_OUT = (0x40)  # OUT | VENDOR | INTERFACE
LIBUSB_VENDOR_INTERFACE_IN  = (0xC0)  # IN  | VENDOR | INTERFACE


def find_dev():
    for dev in usb.core.find(idVendor=VID, find_all=True):
        for cfg in dev:
            for intf in cfg:
                if (intf.bInterfaceClass == 0xff and
                    intf.bInterfaceSubClass == SUBCLASS and
                    intf.bInterfaceProtocol == PROTOCOL):
                    return dev, intf
    return None, None


def main():
    dev, intf = find_dev()
    if not dev:
        sys.exit("no raiden_debug_spi interface found on a 0x18D1 device")
    print(f"Found device VID:PID = 0x{dev.idVendor:04x}:0x{dev.idProduct:04x}")
    print(f"  interface number: {intf.bInterfaceNumber}")

    # Detach kernel driver if any
    if dev.is_kernel_driver_active(intf.bInterfaceNumber):
        try:
            dev.detach_kernel_driver(intf.bInterfaceNumber)
            print("  detached kernel driver")
        except Exception as e:
            print(f"  detach err (ignored): {e}")

    # Claim
    usb.util.claim_interface(dev, intf.bInterfaceNumber)

    # Find bulk endpoints
    ep_in = ep_out = None
    for ep in intf:
        if usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK:
            if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN:
                ep_in = ep
            else:
                ep_out = ep
    if not ep_in or not ep_out:
        sys.exit(f"missing bulk endpoints (in={ep_in}, out={ep_out})")
    print(f"  ep_in = 0x{ep_in.bEndpointAddress:02x}, ep_out = 0x{ep_out.bEndpointAddress:02x}")

    # Try enable with various wIndex values + recipients
    n = None
    candidates = [
        (LIBUSB_VENDOR_INTERFACE_OUT, intf.bInterfaceNumber, 0),
        (LIBUSB_VENDOR_INTERFACE_OUT, 0, 0),
        (LIBUSB_VENDOR_INTERFACE_OUT, intf.bInterfaceNumber, 1),
        (0x41, intf.bInterfaceNumber, 0),    # OUT|VENDOR|RECIPIENT_INTERFACE alt
        (0x42, 0, 0),                         # OUT|VENDOR|RECIPIENT_ENDPOINT (ep 0)
        (0x40, 0, 0),                         # OUT|VENDOR|RECIPIENT_DEVICE
    ]
    for i, (bmRT, wIdx, wValue) in enumerate(candidates):
        try:
            n = dev.ctrl_transfer(
                bmRequestType=bmRT, bRequest=REQ_ENABLE,
                wValue=wValue, wIndex=wIdx, data_or_wLength=0,
                timeout=1000)
            print(f"  enabled bridge (bmRT=0x{bmRT:02x}, wIndex={wIdx}, wValue={wValue}): returned {n}")
            break
        except usb.core.USBError as e:
            print(f"  attempt {i+1} (bmRT=0x{bmRT:02x}, wIndex={wIdx}, wValue={wValue}) err: {e}")
            time.sleep(0.2)
    if n is None:
        sys.exit("could not enable SPI bridge after all variants")

    def spi(write_bytes, read_count, timeout=1000):
        """Send a SPI command. write_bytes is bytes to send, read_count
        is bytes expected back."""
        write_count = len(write_bytes)
        assert write_count <= 62 and read_count <= 62
        pkt = bytes([write_count, read_count]) + write_bytes
        ep_out.write(pkt, timeout=timeout)
        rx = bytes(ep_in.read(read_count + 2, timeout=timeout))
        status = rx[0] | (rx[1] << 8)
        return status, rx[2:2 + read_count]

    # Read JEDEC ID (0x9F): write 1, read 3
    try:
        st, rid = spi(b"\x9f", 3)
        print(f"  RDID (0x9F): status=0x{st:04x} id={rid.hex()}")
    except Exception as e:
        print(f"  RDID err: {e}")

    # Read Status Register (0x05): write 1, read 1
    st, sr = spi(b"\x05", 1)
    print(f"  RDSR before: status=0x{st:04x} SR={sr[0]:#04x} (BP bits = {(sr[0] >> 2) & 0xf})")

    # Send WREN
    st, _ = spi(b"\x06", 0)
    print(f"  WREN: status=0x{st:04x}")

    # Send WRSR with value 0x00
    st, _ = spi(b"\x01\x00", 0)
    print(f"  WRSR 0x00: status=0x{st:04x}")

    # Wait until BUSY clear
    for i in range(20):
        time.sleep(0.05)
        st, sr = spi(b"\x05", 1)
        if not (sr[0] & 0x01):
            break
    print(f"  RDSR after wait: status=0x{st:04x} SR={sr[0]:#04x}")

    # Read SR again to confirm
    st, sr = spi(b"\x05", 1)
    print(f"  RDSR final: SR={sr[0]:#04x}")

    # Disable bridge
    dev.ctrl_transfer(
        bmRequestType=LIBUSB_VENDOR_INTERFACE_OUT,
        bRequest=REQ_DISABLE,
        wValue=0,
        wIndex=intf.bInterfaceNumber,
        data_or_wLength=0,
        timeout=1000,
    )
    print("  disabled bridge")

    usb.util.release_interface(dev, intf.bInterfaceNumber)
    # Don't reattach kernel driver — leave free for flashrom

    if sr[0] & 0xfc:
        print(f"!! SR still has protect bits set: 0x{sr[0]:02x}")
        sys.exit(1)
    else:
        print("✓ SR cleared; flashrom should now be able to write")


if __name__ == "__main__":
    main()

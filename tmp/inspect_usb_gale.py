#!/usr/bin/env python3
import usb.core, usb.util

for dev in usb.core.find(idVendor=0x18D1, find_all=True):
    print(f"=== Device 0x{dev.idVendor:04x}:0x{dev.idProduct:04x}")
    for cfg in dev:
        print(f"  config {cfg.bConfigurationValue}")
        for intf in cfg:
            print(f"    intf {intf.bInterfaceNumber}, alt {intf.bAlternateSetting}: "
                  f"class=0x{intf.bInterfaceClass:02x} sub=0x{intf.bInterfaceSubClass:02x} proto=0x{intf.bInterfaceProtocol:02x}")
            for ep in intf:
                print(f"      ep 0x{ep.bEndpointAddress:02x} type={usb.util.endpoint_type(ep.bmAttributes)}")

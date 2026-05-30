#!/usr/bin/env python3
d = open("/home/tim/local/gwifi/depthcharge-ipq4019/tmp/cur-shared.bin", "rb").read()
print("size", len(d))
# flashrom -r writes the FULL chip image; we look at the region offset
r = d[0x550000:0x550000+128]
print("SHARED_DATA first 128 bytes:", r.hex())
print("decoded:", r.decode("latin1", "replace"))

ff = sum(1 for b in d[0x550000:0x560000] if b == 0xff)
zz = sum(1 for b in d[0x550000:0x560000] if b == 0)
print(f"SHARED_DATA: ff={ff} 00={zz} other={0x10000-ff-zz}")

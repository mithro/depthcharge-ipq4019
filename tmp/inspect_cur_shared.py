#!/usr/bin/env python3
d = open("/home/tim/local/gwifi/depthcharge-ipq4019/tmp/cur-shared.bin", "rb").read()
print("size", len(d))
# When -r ... -i SHARED_DATA, flashrom 1.4 outputs ONLY the region data (not full 8MB).
# So it's 64KB starting at offset 0.
r = d[:64]
print("first 64 bytes:", r.hex())
print("decoded:", r.decode("latin1", "replace"))
ff = sum(1 for b in d if b == 0xff)
zz = sum(1 for b in d if b == 0)
print(f"ff={ff} 00={zz} other={len(d)-ff-zz}")

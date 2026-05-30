#!/usr/bin/env python3
"""Show /configurations/config@1 raw property bytes."""
import libfdt, sys

src = sys.argv[1] if len(sys.argv) > 1 else "tmp/openwrt-gale-patched.itb"
fit = libfdt.Fdt(open(src, "rb").read())
print(f"totalsize: {fit.totalsize()}")

images = fit.subnode_offset(0, "images")
print("\nimages children:")
c = fit.first_subnode(images, libfdt.QUIET_NOTFOUND)
while c >= 0:
    print(f"  {fit.get_name(c)}")
    c = fit.next_subnode(c, libfdt.QUIET_NOTFOUND)

configs = fit.subnode_offset(0, "configurations")
cfg = fit.subnode_offset(configs, "config@1")
o = fit.first_property_offset(cfg, libfdt.QUIET_NOTFOUND)
print("\nconfig@1 props:")
while o >= 0:
    p = fit.get_property_by_offset(o)
    v = bytes(p)
    print(f"  {p.name!r} = {v.hex()} ({len(v)} bytes, raw: {v!r})")
    o = fit.next_property_offset(o, libfdt.QUIET_NOTFOUND)

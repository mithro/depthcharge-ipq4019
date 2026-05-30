#!/usr/bin/env python3
"""Extract /images/fdt-1's data blob from a FIT to a standalone .dtb file."""
import sys, libfdt

src = sys.argv[1]
dst = sys.argv[2] if len(sys.argv) > 2 else src.replace(".itb", ".dtb")

fit = libfdt.Fdt(open(src, "rb").read())
images = fit.subnode_offset(0, "images")
fdt_off = fit.subnode_offset(images, "fdt-1")
inner = bytes(fit.getprop(fdt_off, "data"))
open(dst, "wb").write(inner)
print(f"wrote {dst}: {len(inner)} bytes")

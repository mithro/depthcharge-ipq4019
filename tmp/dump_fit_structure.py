#!/usr/bin/env python3
"""Dump full FIT structure for diagnostics."""
import libfdt, sys

src = sys.argv[1]
fit = libfdt.Fdt(open(src, "rb").read())

def walk(off, depth=0):
    name = fit.get_name(off)
    print(("  " * depth) + "/" + name)
    o = fit.first_property_offset(off, libfdt.QUIET_NOTFOUND)
    while o >= 0:
        p = fit.get_property_by_offset(o)
        n = p.name
        try:
            v = bytes(p)
        except Exception as e:
            v = b"<err>"
        if n == "data":
            print(("  " * (depth+1)) + f"{n} = <{len(v)} bytes>")
        else:
            # try string
            if v.endswith(b"\x00"):
                try:
                    s = v.rstrip(b"\x00").decode("utf-8")
                    print(("  " * (depth+1)) + f"{n} = {s!r}")
                except Exception:
                    print(("  " * (depth+1)) + f"{n} = {v.hex()}")
            else:
                print(("  " * (depth+1)) + f"{n} = {v.hex()}")
        o = fit.next_property_offset(o, libfdt.QUIET_NOTFOUND)
    c = fit.first_subnode(off, libfdt.QUIET_NOTFOUND)
    while c >= 0:
        walk(c, depth+1)
        c = fit.next_subnode(c, libfdt.QUIET_NOTFOUND)

walk(0)

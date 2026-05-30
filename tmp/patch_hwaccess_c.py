#!/usr/bin/env python3
"""Patch flashrom-cros hwaccess.c to recognize aarch64 the same as arm."""
import sys
PATH = sys.argv[1] if len(sys.argv) > 1 else "/home/tim/local/gwifi/depthcharge-ipq4019/flashrom-cros/hwaccess.c"
old = "#elif defined (__arm__)"
new = "#elif defined (__arm__) || defined(__aarch64__)"
s = open(PATH).read()
if old not in s:
    sys.exit("expected pattern not found")
s2 = s.replace(old, new, 1)
open(PATH, "w").write(s2)
print("patched")

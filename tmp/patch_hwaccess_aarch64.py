#!/usr/bin/env python3
"""Patch flashrom-cros hwaccess.h to recognize aarch64 the same as arm."""
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "/home/tim/local/gwifi/depthcharge-ipq4019/flashrom-cros/hwaccess.h"
OLD = "#elif defined(__arm__)\n\n/* Non memory mapped I/O is not supported on ARM. */"
NEW = "#elif defined(__arm__) || defined(__aarch64__)\n\n/* Non memory mapped I/O is not supported on ARM. */"

s = open(PATH).read()
if OLD not in s:
    raise SystemExit("expected pattern not found")
s2 = s.replace(OLD, NEW, 1)
open(PATH, "w").write(s2)
print(f"patched {PATH}")

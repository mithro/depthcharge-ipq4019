#!/usr/bin/env python3
"""Patch flashrom-cros programmer.h to add __aarch64__ to ifdef gating
SPI_CONTROLLER_BITBANG so the build succeeds on Pi (aarch64).
"""
import sys
PATH = sys.argv[1] if len(sys.argv) > 1 else "/home/tim/local/gwifi/depthcharge-ipq4019/flashrom-cros/programmer.h"
old = "(defined(__i386__) || defined(__x86_64__) || defined(__arm__))"
new = "(defined(__i386__) || defined(__x86_64__) || defined(__arm__) || defined(__aarch64__))"
s = open(PATH).read()
if old not in s:
    sys.exit("expected pattern not found")
n = s.count(old)
s2 = s.replace(old, new)
open(PATH, "w").write(s2)
print(f"replaced {n} occurrences")

<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Building the gale depthcharge netboot payload (from scratch) — WORKING RECIPE

Verified working 2026-05-28 on Ubuntu (GCC 13, GNU make 4.3). Produces
`depthcharge/build/netboot.payload` (a CBFS SELF payload) for board **gale**.
Because the chromiumos trees are 2016-era, a modern toolchain needs the fixes
below. `depthcharge` is vendored as a submodule (the
[mithro/depthcharge](https://github.com/mithro/depthcharge) fork, which already
carries the driver + these fixes); the other trees are gitignored build-time
clones at branch **`firmware-gale-8281.B`**. Ready-to-apply patch artifacts for
the fixes below are in [`../patches/`](../patches/README.md).

## 0. Trees (all `firmware-gale-8281.B`)
```
coreboot         9ff56abe09ac   (for payloads/libpayload + util/cbfstool)
depthcharge      b88cbbe1bb16   (the payload we build)
vboot_reference  8fc5916c7f66   (VB_SOURCE; depthcharge builds the fwlib from it)
flashrom-cros    59543cd        (cros flashrom 0.9.4 — the contemporaneous raiden tool)
```

## 1. Toolchain shim (ARMv7 bare-metal)
The host has `arm-none-eabi-*` but coreboot's `util/xcompile` searches for
`armv7a-eabi-*`. Create a shim dir on its default search path and pin `-march`:
```
coreboot/util/crossgcc/xgcc/bin/armv7a-eabi-<tool>  ->  /usr/bin/arm-none-eabi-<tool>
# EXCEPT armv7a-eabi-gcc is a wrapper script:
#   #!/bin/sh
#   exec /usr/bin/arm-none-eabi-gcc -march=armv7-a "$@"
```
`-march=armv7-a` is required or CP15 (`mrc/mcr p15`) won't assemble in Thumb mode.

## 2. libpayload  (coreboot/payloads/libpayload)
- Config = `configs/defconfig-arm` plus: `CONFIG_LP_IPQ40XX_SERIAL_CONSOLE=y`,
  `CONFIG_LP_TIMER_IPQ40XX=y`, `# CONFIG_LP_TIMER_NONE` off, **`CONFIG_LP_CHROMEOS=y`**
  (needed for `lib_sysinfo.macs/num_macs`), **`# CONFIG_LP_VIDEO_CONSOLE` off**
  (gale is headless; depthcharge provides the `video_console_init` stub — else a
  duplicate-symbol link error). Saved as `configs/config.gale`.
- Makefile.inc:67 — drop `-Werror`, add `-fcommon` (GCC10+ `-fno-common` default
  breaks tentative-definition globals).
```
make distclean
make KBUILD_DEFCONFIG=configs/config.gale defconfig
make -j$(nproc)
make install DESTDIR=$PWD/install            # -> install/libpayload
```

## 3. cbfstool (coreboot/util/cbfstool)
- Needs vboot headers: symlink `coreboot/3rdparty/vboot -> ../vboot_reference`.
- Makefile.inc:62 — drop `-Werror` (`TOOLCFLAGS`).
```
make -C coreboot/util/cbfstool -j4        # -> cbfstool, fmaptool, rmodtool
```

## 4. depthcharge + vboot fwlib
- depthcharge Makefile:130 — drop `-Werror`, add `-fcommon`.
- vboot_reference Makefile:131 — `WERROR :=` (empty).
```
export LIBPAYLOAD_DIR=$PWD/coreboot/payloads/libpayload/install/libpayload
export VB_SOURCE=$PWD/vboot_reference
export PATH=$PWD/coreboot/util/cbfstool:$PATH      # for cbfstool
cd depthcharge
make BOARD=gale defconfig LIBPAYLOAD_DIR=$LIBPAYLOAD_DIR
make BOARD=gale netboot_unified LIBPAYLOAD_DIR=$LIBPAYLOAD_DIR VB_SOURCE=$VB_SOURCE -j$(nproc)
# -> build/netboot.elf (ARM EABI5), build/netboot.bin (LZMA), build/netboot.payload (CBFS SELF)
```
`dev_unified` builds the dev image (normal boot + Ctrl+N netboot) the same way.

## 5. cros flashrom (flashrom-cros) — for raiden SPI over SuzyQ
Deps: `libpci-dev libftdi1-dev libfdt-dev libusb-1.0-0-dev`.
- Makefile:38 — `-Werror` -> `-Wno-error -fcommon`.
- search.c — add `#include <limits.h>` (CHAR_BIT).
- Makefile:266 — `USE_BIG_LOCK=0 USE_CROS_EC_LOCK=0` (avoid /run/lock lockfile).
```
make clean && make CONFIG_RAIDEN_DEBUG_SPI=yes -j4    # -> ./flashrom (raiden_debug_spi)
```

## Summary of why each fix
Every failure was modern-toolchain vs 2016-source: missing `armv7a-eabi` prefix,
no `-march`, `-Werror` on new warnings, GCC10 `-fno-common`, headless video stub
collision, `CHROMEOS` sysinfo gating, vboot header path, and a stale lockfile.

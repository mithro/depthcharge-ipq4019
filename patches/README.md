<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Patches

Concrete patch artifacts for this project. See `../docs/build.md` for the full
from-scratch build recipe and the rationale behind every change.

## depthcharge (forked — not patched here)

The IPQ4019 net driver lives in a proper fork, vendored as the `depthcharge/`
submodule: <https://github.com/mithro/depthcharge> (branch `firmware-gale-8281.B`).
`0001-add-ipq4019-net-driver.patch` is kept here as the standalone driver diff
for reference / upstream submission.

## Build-portability patches for the other vendored trees

These three ChromeOS trees are 2016-era and need small fixes to build on a
modern toolchain (GCC 10+ `-fno-common`, `-Werror` on new warnings, OpenSSL 3
API). They are **gitignored build-time clones**, not submodules. To reproduce:
clone each upstream at the pinned commit on branch `firmware-gale-8281.B`, then apply
the matching patch:

```sh
# coreboot
git clone https://chromium.googlesource.com/chromiumos/third_party/coreboot coreboot
git -C coreboot checkout 9ff56abe09acaaef355ce83282ae32c825bbe5ca
git -C coreboot apply ../patches/coreboot-build-portability.patch

# vboot_reference
git clone https://chromium.googlesource.com/chromiumos/platform/vboot_reference vboot_reference
git -C vboot_reference checkout 8fc5916c7f66627be26203aa4f0d800a266b4b4b
git -C vboot_reference apply ../patches/vboot_reference-build-portability.patch
```

| Tree | Upstream | Pinned commit | Patch | Extra |
|------|----------|---------------|-------|-------|
| `coreboot` | https://chromium.googlesource.com/chromiumos/third_party/coreboot | `9ff56abe09ac` | `coreboot-build-portability.patch` | `coreboot-libpayload-config.gale` → `payloads/libpayload/configs/config.gale` |
| `vboot_reference` | https://chromium.googlesource.com/chromiumos/platform/vboot_reference | `8fc5916c7f66` | `vboot_reference-build-portability.patch` | — |

> Note: coreboot also needs its own `3rdparty/vboot` symlink and the generated
> `util/cbfstool/fmd_{parser,scanner}.h` (bison/flex output) — both are build
> steps, not source changes, so they are not included here. See `docs/build.md`.


#!/usr/bin/env python3
"""Load openwrt-gale.itb, extract its inner DTB, apply a set of DTB
patches via pylibfdt, regenerate the FIT with new hashes, write
openwrt-gale-patched.itb.

This avoids any flash changes on gale itself — we only modify the file
that dnsmasq serves over TFTP.

Patches applied (toggle via PATCHES dict at top of file):

  - disable_wifi:      wifi@a000000 and wifi@a800000 → status="disabled"
                       (escapes the ath10k_pci AHB-probe panic so the
                        initramfs reaches a shell)

  - strip_wifi_pinctrl: drop pinctrl-0/pinctrl-names from wifi@a800000
                       (in case the pinctrl-apply is the panic site)

  - add_coreboot_reg:  add /firmware/coreboot with reg=<0x87000000 0x280000>
                       (depthcharge's runtime fixup will overwrite this
                       reg, so this only matters if the runtime fixup is
                       producing zero/empty reg)

The output .itb has the same overall FIT layout as the input — same
kernel image, just a new fdt-1 with refreshed hashes.
"""
import sys, os, hashlib, zlib
sys.path.insert(0, "/usr/lib/python3/dist-packages")  # in case venv pylibfdt
import libfdt

ROOT = "/home/tim/local/gwifi/depthcharge-ipq4019"
SRC  = f"{ROOT}/tmp/openwrt-gale.itb"
OUT  = f"{ROOT}/tmp/openwrt-gale-patched.itb"

# Toggle patches here. Each PATCH can also be overridden via env var
# FIT_<KEY_UPPER> ("on"/"off" for wifi nodes, "true"/"false" for booleans).
PATCHES = {
    # Wifi node enable state. "off"=status=disabled, "on"=status=okay.
    # Default = leave as upstream ("on" implicitly in our DTS).
    "wifi_a000000":          "off",     # 5 GHz (no pinctrl on this node)
    "wifi_a800000":          "off",     # 2.4 GHz (has pinctrl-0=<0x1c>)
    "strip_wifi_pinctrl":    False,     # also drop pinctrl-0/names from a800000
    "add_coreboot_reg":      True,
}

# Apply env-var overrides.
for _k in list(PATCHES.keys()):
    _env_k = "FIT_" + _k.upper()
    if _env_k in os.environ:
        _v = os.environ[_env_k]
        if _v in ("on", "off"): PATCHES[_k] = _v
        elif _v.lower() in ("true", "1", "yes"): PATCHES[_k] = True
        elif _v.lower() in ("false", "0", "no"): PATCHES[_k] = False
        else: PATCHES[_k] = _v


def crc32_of(data: bytes) -> int:
    return zlib.crc32(data) & 0xffffffff


def patch_dtb(dtb: bytes) -> bytes:
    """Apply the configured DTB patches and return the (re-flattened) DTB."""
    fdt = libfdt.Fdt(bytearray(dtb))  # mutable
    # libfdt mutating APIs require the FDT to have headroom; pack/resize.
    fdt.resize(len(dtb) + 4096)

    def set_status(path, status):
        try:
            off = fdt.path_offset(path)
        except libfdt.FdtException as e:
            print(f"  [skip] {path}: {e}")
            return
        fdt.setprop(off, "status", status.encode() + b"\x00")
        print(f"  [set] {path} status = {status!r}")

    def del_prop(path, prop):
        try:
            off = fdt.path_offset(path)
        except libfdt.FdtException:
            return
        try:
            fdt.delprop(off, prop)
            print(f"  [del] {path}/{prop}")
        except libfdt.FdtException:
            pass

    def add_coreboot_node():
        try:
            firmware_off = fdt.path_offset("/firmware")
        except libfdt.FdtException:
            root = fdt.path_offset("/")
            firmware_off = fdt.add_subnode(root, "firmware")
            print("  [add] /firmware")
        # Make sure /firmware has empty `ranges` so child reg= can translate.
        try:
            fdt.getprop(firmware_off, "ranges")
        except libfdt.FdtException:
            fdt.setprop(firmware_off, "ranges", b"")
            print("  [add] /firmware/ranges = <empty>")
        # Add or replace the coreboot subnode.
        try:
            cb_off = fdt.subnode_offset(firmware_off, "coreboot")
        except libfdt.FdtException:
            cb_off = fdt.add_subnode(firmware_off, "coreboot")
            print("  [add] /firmware/coreboot")
        fdt.setprop(cb_off, "compatible", b"coreboot\x00")
        # reg = <0x87000000 0x280000> covering all of CBMEM up to
        # memlayout_cbmem_top (which is 0x87280000 per coreboot's
        # soc/qualcomm/ipq40xx/include/soc/memlayout.ld).
        reg = (0x87000000).to_bytes(4, "big") + (0x00280000).to_bytes(4, "big")
        fdt.setprop(cb_off, "reg", reg)
        print(f"  [set] /firmware/coreboot reg = 0x87000000/0x280000")

    for node_name in ("wifi_a000000", "wifi_a800000"):
        want = PATCHES.get(node_name)
        if want is None:
            continue
        dt_path = "/soc/" + node_name.replace("_", "@")
        if want == "off":
            set_status(dt_path, "disabled")
        elif want == "on":
            set_status(dt_path, "okay")

    if PATCHES.get("strip_wifi_pinctrl"):
        del_prop("/soc/wifi@a800000", "pinctrl-0")
        del_prop("/soc/wifi@a800000", "pinctrl-names")

    if PATCHES.get("add_coreboot_reg"):
        add_coreboot_node()

    # Pack and return.
    fdt.pack()
    return bytes(fdt.as_bytearray())


def rebuild_fit(orig: bytes, new_inner_dtb: bytes) -> bytes:
    """Build a new FIT by cloning the outer FIT and replacing /images/fdt-1's
    `data` property + its hash subnodes.

    pylibfdt can edit FDTs in-place. We resize, replace data, recompute
    hashes, pack."""
    fdt = libfdt.Fdt(bytearray(orig))
    # Outer FIT is itself a flat DT. Need plenty of headroom because data
    # property might grow (or shrink).
    extra = max(0, len(new_inner_dtb) - len(orig)) + 8192
    fdt.resize(len(orig) + extra)

    images_off = fdt.subnode_offset(0, "images")
    fdt_off = fdt.subnode_offset(images_off, "fdt-1")

    fdt.setprop(fdt_off, "data", new_inner_dtb)
    print(f"  [set] /images/fdt-1/data = <{len(new_inner_dtb)} bytes>")

    # Refresh hashes (CRC32 + SHA1).
    new_crc = crc32_of(new_inner_dtb)
    new_sha = hashlib.sha1(new_inner_dtb).digest()

    # Walk hash subnodes under fdt-1
    sub = fdt.first_subnode(fdt_off, libfdt.QUIET_NOTFOUND)
    while sub >= 0:
        name = fdt.get_name(sub)
        try:
            algo_b = fdt.getprop(sub, "algo")
            algo = bytes(algo_b).rstrip(b"\x00").decode()
        except libfdt.FdtException:
            sub = fdt.next_subnode(sub, libfdt.QUIET_NOTFOUND)
            continue
        if algo == "crc32":
            fdt.setprop(sub, "value", new_crc.to_bytes(4, "big"))
            print(f"  [set] /images/fdt-1/{name}/value = crc32 0x{new_crc:08x}")
        elif algo == "sha1":
            fdt.setprop(sub, "value", new_sha)
            print(f"  [set] /images/fdt-1/{name}/value = sha1 {new_sha.hex()}")
        elif algo == "sha256":
            new_sha256 = hashlib.sha256(new_inner_dtb).digest()
            fdt.setprop(sub, "value", new_sha256)
            print(f"  [set] /images/fdt-1/{name}/value = sha256 {new_sha256.hex()}")
        sub = fdt.next_subnode(sub, libfdt.QUIET_NOTFOUND)

    fdt.pack()
    return bytes(fdt.as_bytearray())


def main():
    print(f"=== Patches: {PATCHES}")
    print(f"=== Load: {SRC}")
    with open(SRC, "rb") as f:
        fit = f.read()
    print(f"  FIT size: {len(fit)} bytes")

    # Extract inner DTB
    fdt = libfdt.Fdt(bytearray(fit))
    images_off = fdt.subnode_offset(0, "images")
    fdt_off = fdt.subnode_offset(images_off, "fdt-1")
    inner = bytes(fdt.getprop(fdt_off, "data"))
    print(f"  Inner DTB size: {len(inner)} bytes")

    # Patch inner DTB
    print("=== Patch DTB")
    patched_inner = patch_dtb(inner)
    print(f"  patched DTB size: {len(patched_inner)} bytes")

    # Rebuild FIT
    print("=== Rebuild FIT")
    new_fit = rebuild_fit(fit, patched_inner)
    print(f"  new FIT size: {len(new_fit)} bytes")

    with open(OUT, "wb") as f:
        f.write(new_fit)
    print(f"=== Wrote {OUT}")
    print(f"  sha256: {hashlib.sha256(new_fit).hexdigest()}")


if __name__ == "__main__":
    main()

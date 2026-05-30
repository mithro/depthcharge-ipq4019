#!/bin/sh
# Build a FIT using mkimage with kernel + dtb + ramdisk (pivot overlay).
# The dtb here is the patched one (wifi enabled, coreboot reg) and the
# ramdisk is the xz-compressed pivot overlay.
set -e

ROOT=/home/tim/local/gwifi/depthcharge-ipq4019/tmp
KERNEL=$ROOT/openwrt-gale-kernel.bin
DTB=$ROOT/openwrt-gale-patched.dtb
RAMDISK=$ROOT/openwrt-pivot-overlay.cpio
OUT=$ROOT/openwrt-gale-mkimage.itb

# Extract the kernel binary from the FIT (we already have the dtb from earlier)
if [ ! -f "$KERNEL" ]; then
    echo "=== Extract kernel from FIT ==="
    uv run --with pylibfdt python3 - <<'PY'
import libfdt
fit = libfdt.Fdt(open("/home/tim/local/gwifi/depthcharge-ipq4019/tmp/openwrt-gale.itb","rb").read())
images = fit.subnode_offset(0, "images")
kernel = fit.subnode_offset(images, "kernel-1")
data = bytes(fit.getprop(kernel, "data"))
open("/home/tim/local/gwifi/depthcharge-ipq4019/tmp/openwrt-gale-kernel.bin", "wb").write(data)
print(f"kernel: {len(data)} bytes")
PY
fi

# Build the patched DTB (this should already exist)
if [ ! -f "$DTB" ]; then
    echo "patched DTB missing — run patch_fit_dtb.py first"; exit 1
fi

# Write an its file
ITS=$ROOT/openwrt-gale.its
cat > "$ITS" <<EOF
/dts-v1/;
/ {
    description = "ARM OpenWrt FIT";
    #address-cells = <1>;
    images {
        kernel-1 {
            description = "ARM OpenWrt Linux";
            data = /incbin/("$KERNEL");
            type = "kernel";
            arch = "arm";
            os = "linux";
            compression = "none";
            load = <0x80208000>;
            entry = <0x80208000>;
            hash-1 { algo = "crc32"; };
            hash-2 { algo = "sha1"; };
        };
        fdt-1 {
            description = "ARM OpenWrt gale DTB (patched)";
            data = /incbin/("$DTB");
            type = "flat_dt";
            arch = "arm";
            compression = "none";
            hash-1 { algo = "crc32"; };
            hash-2 { algo = "sha1"; };
        };
        ramdisk-1 {
            description = "Pivot overlay initramfs (xz)";
            data = /incbin/("$RAMDISK");
            type = "ramdisk";
            arch = "arm";
            os = "linux";
            compression = "none";
            hash-1 { algo = "sha1"; };
        };
    };
    configurations {
        default = "config@1";
        config@1 {
            description = "OpenWrt google_wifi";
            kernel = "kernel-1";
            fdt = "fdt-1";
            ramdisk = "ramdisk-1";
        };
    };
};
EOF

echo "=== mkimage -f $ITS $OUT ==="
mkimage -f "$ITS" "$OUT"
ls -la "$OUT"

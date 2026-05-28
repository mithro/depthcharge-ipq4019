<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# gale IPQ4019 driver — on-hardware bring-up log

Empirical findings from bringing the driver up on a physical Google Wifi over
SuzyQ (2026-05-28). Corrects/extends `hardware.md`.

## Boot chain (observed)

- coreboot **RO** (WP_RO, hardware-protected) runs first → vboot/verstage.
- **Normal/dev mode** → loads the **RW** firmware body from **`FW_MAIN_A`** (CBFS
  `fallback/payload` @ 0x73ac0 within the region @ 0x402000). The RW preamble has
  **`USE_RO_NORMAL`**, which means *"load the RW body but skip verifying it"* (NOT
  "use RO instead"). **Consequence: you can swap the RW `fallback/payload` without
  re-signing** — the stock-signed keyblock/preamble stay valid (no body hash).
- **Recovery mode** → runs the **RO** depthcharge (`COREBOOT` region `fallback/payload`
  @ 0x46800). Replacing it needs no signing (RO is HW-trusted) but writing it needs
  the WP_RO region writable.
- Headless gale synthesizes only ^U/^D from the dev button (no ^N), so true netboot
  needs the **`netboot` payload as the loaded payload** (its `main`=`netboot_entry`
  auto-netboots) — which is what we flash in.

## Flashing over SuzyQ (raiden) — what works / pitfalls

- Read: `gale power off && sudo flashrom -p raiden_debug_spi -r f` — **no `target=`**,
  **system flashrom 1.3.0** (SFDP). Verified == stock.
- `FW_MAIN_A`/`RW_SECTION_A/B` (≥0x400000) are **outside WP_RO** → writable with the
  AP off, no WP deassert. `COREBOOT`/WP_RO needs WP deasserted (flaky on this EC).
- The flash is only accessible when the **AP CPU is OFF** (`VDD_1P1_CPU_EN=0`) **and**
  recently powered (the EC powers the flash for the bridge). A **crashed/hung AP**
  holds the SPI bus → reads return all-`0x00`. A degraded flash state (after many
  crash/reboot cycles) returns `0x00` and only a **physical VCC power-cycle** clears it.
- No PPPS USB hub here (gale VBUS ~4.4 V/3.8 A comes from a non-uhubctl source), so
  power-cycling is manual / external.

## Driver status

- `src/drivers/net/ipq4019.{c,h}`, `ipq4019_mdio.c`, `ipq4019_psgmii.c` build into the
  gale `netboot.payload` and **ran on hardware (first light)**: reached
  `net_wait_for_link()`.
- Crash on first light was **not the driver** — `dc_usb_initialize` (USB-eth poller /
  unpowered xHCI). **Fixed** by guarding the `usb_eth` poller on
  `CONFIG_DRIVER_NET_ASIX||SMSC95XX` (patch 0001).
- **Not yet exercised:** PSGMII calibration → link → DHCP → TFTP. That's the next
  iterative loop once the fixed image is flashed.

## Netboot payload (the goal target)

`openwrt-25.12.2-ipq40xx-chromium-google_wifi-initramfs-fit-zImage.itb.vboot`
(downloaded) is a **ChromeOS vboot kernel** (`CHROMEOS` magic) wrapping a FIT at
offset **0x10000**.

**Gotcha (caught before it bit us):** depthcharge netboot's `boot()` (ARM,
`src/arch/arm/fit.c`) calls `fit_load(bi->kernel)` which needs a **raw FIT
(`d00dfeed`) at the payload start** — it does NOT strip the vboot/`CHROMEOS`
wrapper. So the `.itb.vboot` would fail `fit_load`. **Fix: extract the raw FIT**
from offset 0x10000 (length = FDT `totalsize` BE@+4) →
`tmp/tftproot/openwrt-gale.itb`. `dumpimage -l` confirms it: kernel-1 = ARM OpenWrt
Linux-6.12.74 (8 MB, embedded initramfs) **load/entry 0x80208000** (== gale
`CONFIG_KERNEL_START`), fdt-1 = `google_wifi` DTB. That raw `.itb` is the netboot
bootfile (`dhcp-boot=openwrt-gale.itb`); the kernel boots its embedded initramfs =
"kernel+initrd". dnsmasq DHCP+TFTP runs on `enx00e04c68016b` (10.42.1.1).

## Next steps

1. (after power-cycle) `tmp/postcycle_flash.py` — quiesce AP, flash fixed driver to
   FW_MAIN_A, dev mode.
2. Reboot + capture: verify PSGMII self-test, link, DHCP round-trip (Phase 1).
3. Start dnsmasq DHCP+TFTP serving the .itb.vboot; verify TFTP download + boot (Phase 2).
4. Iterate on PSGMII/EDMA register tuning as needed (RW-only reflash, fast).

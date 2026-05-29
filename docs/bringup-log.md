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
  AP off, no WP deassert. `COREBOOT`/WP_RO needs WP deasserted via `gpioset WP_L 1` from the EC.
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

---

## Update: SPI bus deadlock after flashing to COREBOOT (RO)

After "first light", I observed that the running payload was the one written into
**`COREBOOT`** (RO), not `FW_MAIN_A` (RW). To pin down behavior I had flashed both
sides; the RO side is what executed (the device boots whatever payload sits inside
the `COREBOOT` CBFS, regardless of what `FW_MAIN_A` contains, on this RW-preamble
configuration). This pivot turned out to be expensive.

### What broke
With the fixed-but-unverified driver in `COREBOOT`, the AP entered an early crash
during the **build before the `usb_eth` guard fix** was in place. Every reset:
`coreboot → my payload → crash inside the AP`. The crashed IPQ4019 holds the SPI
master pins, so the EC's `raiden_debug_spi` bridge can no longer read the chip:
RDID fails, SFDP returns garbage, and bulk reads come back as ~95% zeros.

### Recovery attempts and what we learned

1. **Root-port power-cycle works.** The Super Top hub (gale) is on Bus 003 root
   port 1 of the laptop's xHCI (PCI `0000:00:14.0`); writing `1`/`0` to
   `/sys/bus/usb/devices/3-0:1.0/usb3-port1/disable` cleanly drops and restores
   power to the gale (and only the gale — touchpad, bluetooth, camera, yubikey
   are on other root ports). See `tmp/rootport_cycle.py`.

2. **Catch-the-AP-off approach** (`tmp/cycle_catch_flash.py`): power-cycle, then
   immediately spam `gale power off` to the EC console at ≤10 Hz via a persistent
   serial connection. The bus state improves dramatically — the chip ID reads
   clean (`W25Q64BV/W25Q64CV/W25Q64FV`) — but the bulk read settles at **~62.9%
   zeros**, which is not clean enough for a reliable erase/write/verify cycle.
   Sending ~4000 `gale power off` messages during a single operation did not
   reduce the contention.

3. **Pure flash-rail power** (`tmp/flash_only.py`): force `gpioset VDD_3P3_EN 1`
   with the AP rail (`VDD_1P1_CPU_EN`) at 0 → flashrom reports **No EEPROM/flash
   device found**. The IPQ's SPI pads appear to float/leak when the AP is
   unpowered, corrupting the bus regardless of flash power. So "AP off + flash
   on" is not actually achievable for read purposes on this board.

4. **EC's own `spixfer`**: command syntax is `spixfer rlen <id> <off> <len>`. All
   device indices 0..5 return what look like EC SRAM contents (e.g.,
   `6c1b0020 74bb0008 …`), not flash data — the EC's `spi_devices[]` array does
   not include the AP flash in a usefully exposed way.

5. **Partial-erase attempt**: in the ~63% catch state, `flashrom -w … -i COREBOOT`
   got past detection and attempted multiple erases (4 KB, 64 KB, full); every
   erase verify failed (e.g., "Expected=0xff, Found=0x1f"), but at least some
   bits flipped (suggesting partial erases reached the chip). End state per
   flashrom: *"Your flash chip is in an unknown state."*

6. **After the partial erase the device entered a worse state.** A fresh
   root-port power-cycle now produces:
   - all rails up automatically (EC powers the AP),
   - **AP console completely silent for 10+ seconds** (no coreboot bootblock
     banner — bootrom hangs before any output),
   - no Qualcomm USB device (no SAHARA/EDL fallback on any visible USB port),
   - flashrom writes hang for the full 400 s timeout with no progress (`No
     EEPROM/flash device found` or no output at all).

   Interpretation: the bootblock at offset 0 is partially corrupted enough that
   the IPQ bootrom hangs trying to validate it, and the hung bootrom holds the
   SPI bus more firmly than the earlier `usb_eth` crash did.

### Current best guess

SuzyQ-side recovery is exhausted on this board. The IPQ4019 bootrom on gale
does not appear to fall back to USB-boot (SAHARA/EDL) on a corrupted bootblock —
it just hangs. To recover we likely need a **CH341A SPI clip** on the W25Q64FV
to write the saved stock dump (`/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin`)
back to offsets `0x0–0x800000`.

### Lessons (please don't repeat)

- **Don't flash a known-untested or known-crashing payload into the `COREBOOT`/RO
  region** on a SuzyQ-only-accessible device. Recovery depends on stock RO's
  recovery loop releasing the SPI bus for the EC bridge — if you replace it with
  something that crashes, you lose your only reflash path.
- **Always verify a clean read of the flash *before* every write**, not just
  the first one.
- **Partial erases on a contended bus are worse than no erase at all** — they
  destroy validity without enabling a fresh write.
- Approach A (sign+resign into `FW_MAIN_A`, clear `USE_RO_NORMAL`) is the
  correct recovery strategy once flash access is restored.

### Scratch scripts of record

- `tmp/rootport_cycle.py` — controlled VBUS cycle of the gale.
- `tmp/cycle_catch_flash.py` — power-cycle + catch + (would-be) flash v2.
- `tmp/flash_only.py` — force flash rail on with AP off (didn't help).
- `tmp/post_cycle_probe.py` — observation after a power-cycle.
- `tmp/turn_ap_on.py` — explicit `gale power on` + AP-state probe.
- `tmp/fresh_cycle.py` — fresh cycle, no commands, default behaviour.
- `tmp/probe_state.py` — post-failure GPIO + console + read probe.
- `tmp/layout.txt` — flashrom layout file (bypasses contended FMAP read).
- `tmp/diag_busfidelity.py` — read FMAP × 3, compare-vote vs. stock.
- `tmp/multi_cycle_probe.py` — N cycles, hammer `flashrom --flash-name`, watch USB.
- `tmp/restore_bootblock.py` — multi-cycle attempt to write stock 4KB bootblock.

### Final state (2026-05-28, end of session)

- Multi-cycle probe demonstrated **a brief readable window does exist** —
  in one of four power-cycles, `flashrom --flash-name` detected the chip
  cleanly at **t+0.8 s** after USB-port power restore. 46 of ~58 rapid
  RDID attempts had failed before that one succeeded.
- That detection rate was **not reproducible**. Subsequent runs (multiple
  6–7-cycle batches, 30-second VCC hold-off, EC reboot, various GPIO
  states) recorded **0 detections in 1400+ flashrom RDID attempts**.
- No Qualcomm/EDL USB device ever appeared on any port across all probes
  (so the IPQ4019 bootrom on gale really does not fall back to USB-boot
  on a corrupted bootblock).
- AP UART remained silent throughout.

The cycle-to-cycle degradation pattern (~25 % detection earlier in the
session → 0 % later) strongly suggests the repeated contended writes
this session further degraded chip state (likely partial-write side-
effects on individual cells / status register).

**Conclusion: SuzyQ-side recovery on this gale is no longer feasible.**
The device is bricked from this interface. Recovery requires a CH341A
(or equivalent) SPI flash clip onto the W25Q64FV to write back the saved
stock dump `gale-spi-stock-2026-05-28.bin` (offsets `0x0–0x800000`,
sha256 `735b1c5adc3399d8257915d28b3df0313c3e2f64ab8385297c5b1a7eb10012d9`).

After the device is recovered to stock, **the recommended re-entry is
Approach A**: sign a fresh netboot payload with devkeys, splice it into
`FW_MAIN_A` only (no `COREBOOT` writes), and clear `USE_RO_NORMAL` in the
RW preamble — keep `COREBOOT/RO` strictly pristine so the stock recovery
loop is always there to release the SPI bus.

---

## Late-session followup: hard power cycle via UCSI

User clarified: the whole setup (SuzyQ + gale + ethernet adapters) is
powered through a USB-C hub on the laptop's port0. After a physical
unplug of that hub, the gale briefly responded — `coreboot-... bootblock
start` appeared on AP UART for the first time in many cycles. This
prompted a deeper look at the laptop's USB-C PD controls.

### Mechanism: UCSI CONNECTOR_RESET

- `uhubctl -f` reports the laptop's xHCI root hubs as **"nops"** (no
  per-port power switching) and the gale's Super Top hub as **"ganged"**
  (one global switch, not actually per-port controllable). Neither the
  sysfs `port-disable` interface nor uhubctl can drop VBUS on this
  hardware.
- However, the laptop is a ThinkPad X1 Carbon Gen 11 with `ucsi_acpi`
  driving the Type-C PD controller, and the kernel exposes a debugfs
  command interface at `/sys/kernel/debug/usb/ucsi/USBC000:00/command`.
- Writing the UCSI `CONNECTOR_RESET` command for connector 1 (= `port0`,
  the gale's hub):
  ```
  echo 0x10003 > /sys/kernel/debug/usb/ucsi/USBC000:00/command
  ```
  (`0x03 | (1 << 16)`, where `1 << 16` is the connector number field.)
- This **drops VBUS to the entire hub branch**; the gale, EC, hub, and
  both ethernet adapters all disappear from lsusb. They reappear ~1.25 s
  later cleanly enumerated. Verified `tmp/ucsi_hardcycle.py`.
- Note: `power_role` swap (`echo sink > /sys/class/typec/port0/power_role`)
  returns `I/O error` — the partner advertises PR_Swap support but the
  hub is bus-powered and can't actually source.

This means **we no longer need physical unplug for a hard cycle** in
future sessions on this laptop with this hub layout.

### What we learned about the AP boot state after a clean hard cycle

With UCSI CONNECTOR_RESET + `gale power on`, the AP **does boot** —
significantly further than was previously visible:

- **Default vboot path (Slot B selected)** — boots through bootblock,
  reads FMAP, VBLOCK_B, FW_MAIN_B; loads romstage from FW_MAIN_B's CBFS,
  romstage runs and identifies the W25Q64; tries to load
  `fallback/ramstage` from FW_MAIN_B's CBFS; gets
  **`lzma: Decoding error = 1` / `Ramstage was not loaded!`**.
  → Confirms FW_MAIN_B's compressed ramstage body is corrupted by the
  failed erase.
- **Dev mode + rec off path** — `gale dev on; gale rec off; gale power on`
  triggers `Recovery requested (0x5b — DEV_REQUEST)`; vboot tries to
  load `fallback/romstage` from **COREBOOT's** CBFS (RO region) →
  **`Couldn't load romstage`**.
  → Confirms RO COREBOOT's romstage CBFS entry is also corrupted.
- **`gale rec on` (recovery boot)** — gets only to `bootblock start`
  and halts; nothing further on UART.

In **all three** failure modes the IPQ's QUP stays busy enough that
`flashrom --flash-name` from the EC bridge never gets a clean read
(thousands of probes across many UCSI cycles, all 0 detects).

### So what we learned grounds the earlier conclusion

The failed erase corrupted **both** RW Slot B's ramstage AND RO
COREBOOT's romstage. There is no remaining coreboot path that reaches
depthcharge to yield the SPI bus. The IPQ is "alive enough" to read
flash for itself, but never reaches the bus-yielding payload. CH341A
remains the only recovery path.

The UCSI capability **does** simplify future bring-up post-recovery —
the recipe at `docs/post-recovery-recipe.md` can use
`tmp/ucsi_hardcycle.py` instead of asking the user to physically replug.

---

## Correction (2026-05-29): the "SuzyQ broken" conclusion above was wrong

The earlier conclusion "SuzyQ-side recovery on this gale is no longer
feasible" was procedural failure on my part, not a hardware/architectural
limit. After the CH341A restore to v3, SuzyQ was tested with the procedure
documented in `/home/tim/local/gwifi/gale-spi-flash-backup.md`:

- Read: `gale power off && sudo flashrom -p raiden_debug_spi -r dump.bin`
- Write: `gale power off && sudo flashrom -p raiden_debug_spi -w v3.bin --fmap -i FW_MAIN_B`

Both succeeded (exit=0, 43 s read, 42 s erase+write+verify). All static
regions in the read matched v3.bin byte-for-byte (`tmp/verify_regions.py`).

### Three procedural mistakes that produced the false conclusion

1. **`-c W25Q64BV/W25Q64CV/W25Q64FV`**. The EC bridge does not surface a
   database-matched JEDEC ID; flashrom must detect via SFDP (`Unknown flash
   chip "SFDP-capable chip"`). With `-c` set, RDID returns garbage and
   flashrom aborts with `RDID byte 0 parity violation` / `No EEPROM/flash
   device found`. Every "SuzyQ broken" probe in this log used `-c`.
2. **Pre-flight `flashrom --flash-name` probes before the real operation.**
   flashrom's raiden_debug_spi cleanup re-enables AP power on exit; the
   subsequent write then races a re-powered AP. Use a single atomic
   `gale power off && flashrom -w …`.
3. **Re-running flashrom after a prior flashrom left the AP powered.** Same
   root cause as (2).

### What this means about the rest of this log

- The "degraded flash state" / "physical VCC power-cycle required" framing
  is unfounded. The flash chip was responding correctly all along — my
  probes were just unable to read its response.
- The "AP off + flash on isn't achievable" / "IPQ pads float/leak" hypothesis
  (line 108) is unfounded. `gale power off` from a running AP cleanly
  produces CPU off + flash powered + AP idle (verified via gpioget at
  2026-05-29 14:30 local).
- The choice to use CH341A was correct as **emergency recovery once SPI was
  thought wedged**, but a careful application of the documented SuzyQ
  procedure would have avoided all three CH341A flashes in this session.

The authoritative SuzyQ procedure lives in
`/home/tim/local/gwifi/gale-spi-flash-backup.md`. The doc
`docs/keeping-suzyq-recovery-working.md` summarises the three mistakes and
the correct procedure.

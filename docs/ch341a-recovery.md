<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# CH341A SPI clip recovery — restore stock to the gale's W25Q64FV

This is the physical-recovery procedure. After this, follow
`docs/post-recovery-recipe.md` from Step 1.

## Hardware

- **CH341A USB programmer** (any of the standard "black PCB" or "green
  PCB" variants — vendor:product `1a86:5512`).
- **SOIC-8 test clip / pomona clip** matching the W25Q64FV package.
- **3.3 V level**, NOT 5 V. The W25Q64FV is a 3.3 V part. CH341A boards
  ship with a 5 V/3.3 V jumper or two distinct headers — make sure you
  are on the 3.3 V side, and confirm with a multimeter on VCC vs. GND
  on the clip *before* attaching to the gale.
- **The gale must be powered OFF and unplugged.** The W25Q64FV will be
  parasitically powered through the clip; an additional active VCC on
  the gale itself will fight the clip and may damage either the gale
  or the programmer.

## Locating the chip on the gale

The flash is a Winbond W25Q64FV (8 MiB) in SOIC-8 package. On the Google
WiFi (gale, AC-1304) PCB it is **near the IPQ4019 SoC**, typically labelled
near pin 1 with a small white triangle/dot indicating pin orientation. If
unsure, the device markings on top of the chip should match `W25Q64FV` (or
`25Q64FV` with various suffixes).

Pinout (SOIC-8 top view, pin 1 marked with dot):
```
              ┌──────────┐
       /CS  1 │●         │ 8  VCC (3.3 V)
        DO  2 │          │ 7  /HOLD
      /WP   3 │          │ 6  CLK
       GND  4 │          │ 5  DI
              └──────────┘
```

Match the colored wires on the clip to your CH341A's labelling. Most
clips: red=VCC, black=GND, then the rest are SPI signals.

## Software

Use `flashrom` on the host with the `ch341a_spi` programmer driver
(included in flashrom 1.x). On Ubuntu, the system flashrom (1.3.0) ships
with this driver enabled. Verify:

```
flashrom -p ch341a_spi --list-supported | grep -i 'W25Q64'
```

Should list `W25Q64BV/W25Q64CV/W25Q64FV` (the chip definition that
matches our RDID).

## Step 0 — Sanity check the clip *before* clamping the gale

With the clip attached to **nothing** but the CH341A:

```
sudo flashrom -p ch341a_spi --flash-name
```

Should print `No EEPROM/flash device found.` This confirms the
programmer is recognised; no chip yet because the clip isn't attached.

If flashrom can't even find the programmer: check the `1a86:5512` USB
device (`lsusb | grep 1a86`) and consult flashrom docs.

## Step 1 — Clamp onto the gale's W25Q64FV (gale is powered off + unplugged)

Carefully align pin 1 of the clip with pin 1 of the chip (white dot).
Squeeze the clip firmly. A common failure mode is partial contact —
the chip is correctly identified but reads come back corrupted; if
that happens, re-seat the clip.

Verify identification:

```
sudo flashrom -p ch341a_spi --flash-name
```

Should now print something like:
```
Found Winbond flash chip "W25Q64BV/W25Q64CV/W25Q64FV" (8192 kB, SPI)
on ch341a_spi.
vendor="Winbond" name="W25Q64BV/W25Q64CV/W25Q64FV"
```

## Step 2 — Read back the current contents (for forensics)

Before writing, capture what's currently on the chip. This is the
post-deadlock state — useful if we ever want to reconstruct what
happened, and a safety net in case the user changes their mind about
restoring.

```
sudo flashrom -p ch341a_spi \
    -c "W25Q64BV/W25Q64CV/W25Q64FV" \
    -r /home/tim/local/gwifi/gale-spi-bricked-$(date +%F).bin
```

The read should complete in 30-60s. If the read errors out partway,
re-seat the clip and retry — partial reads do NOT damage the chip.

## Step 3 — Write the stock dump back

The stock image to restore:
- Path: `/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin`
- Size: 8388608 bytes (8 MiB exactly)
- SHA-256: `735b1c5adc3399d8257915d28b3df0313c3e2f64ab8385297c5b1a7eb10012d9`

Verify before flashing:
```
ls -la /home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin
sha256sum /home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin
```

Write + verify in one shot:
```
sudo flashrom -p ch341a_spi \
    -c "W25Q64BV/W25Q64CV/W25Q64FV" \
    -w /home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin
```

flashrom will: read current, erase changed sectors, write, verify.
Expected ~2-4 minutes total. The final line should be `VERIFIED.`

If `VERIFIED` does NOT appear: do NOT remove the clip. Re-run the
command (a partial write is usually recoverable if you don't lose
clip contact between attempts).

## Step 4 — Disconnect and power on

Carefully remove the clip. Reconnect the SuzyQ cable and power up the
gale. Continue with `docs/post-recovery-recipe.md` from Step 1.

## Troubleshooting

- **Won't identify chip**: check 3.3 V vs 5 V jumper, re-seat clip,
  verify pin 1 orientation, try a fresh USB cable (CH341A boards
  are sensitive to underpowered USB-2 ports).
- **Identifies but verify fails**: this is almost always loose clip
  contact. Re-seat and retry. If it persists, the chip may have
  real damage; try `-c W25Q64JV-.Q` instead (different chip definition
  for the same RDID — newer variant).
- **Verify shows specific failed bytes**: rewrite only the failed
  region using `flashrom -E` (erase whole chip) then `-w` again.
- **CH341A board itself is suspect**: many cheap boards drive the
  SPI pins via a 1.8K pull-up resistor that's too weak for some
  chips. Try adding a 10K pull-up to /CS if RDID reads are flaky.

## After successful restore

Proceed to `docs/post-recovery-recipe.md` — every step from there
through "OpenWrt initramfs login:" should run mechanically given
the pre-flight bug fixes already committed (`0a3f349`, `6d5a3b0`,
`eac9a9d`, `b9eb473`).

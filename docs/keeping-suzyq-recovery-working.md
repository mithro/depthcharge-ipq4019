<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Keeping the Google Wifi (gale) puck always reflashable via SuzyQ

## TL;DR

**SuzyQ flash on the gale is NOT a reliable software-only recovery mechanism**
once the chip carries non-stock firmware. This document records the rules and
procedures that maximise your chance of avoiding the emergency state where
CH341A becomes necessary — but it cannot guarantee SuzyQ alone is sufficient.

**Bring a CH341A SOIC-8 clip + 3.3 V programmer to every gale session.** Use
SuzyQ when it works (typically with stock firmware) and accept CH341A is the
deterministic recovery for any custom-RW state.

---

## Why this matters

The gale's SPI flash (Winbond W25Q64FV at U45) is a single physical chip
electrically shared between the IPQ4019 SoC's QUP SPI master and the EC's
"raiden_debug_spi" bridge that the SuzyQ cable exposes. There's no hardware
bus mux to disconnect the AP. So whenever the IPQ is actively using the bus,
the EC's bridge can't reliably get clean access. With the device in stock
firmware, the chrome-firmware stock recovery loop yields the bus briefly
between iterations and SuzyQ writes succeed. With any non-stock RW firmware
that doesn't exhibit the same yield pattern, SuzyQ reads return all-zeros
("RDID byte 0 parity violation").

## The single rule that gives the best SuzyQ recovery odds

**Never modify the `COREBOOT` region** (`0x000000–0x300000` of the chip).

`COREBOOT` is the WP_RO region. Stock RO depthcharge lives here. As long as
it remains byte-identical to
`/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin[0:0x300000]`, the device
can always be force-booted into recovery mode (`gale rec on`) where the stock
recovery loop runs from RO. From there, **on a stock-like chip**, the legacy
flashrom procedure (`flash_rw.py`) has worked in this session. With dev keys
in GBB and dev-signed VBLOCKs, the same procedure has failed — but we don't
fully understand why, so keep COREBOOT intact regardless.

The pragmatic implication: if you're doing dev work, modify only
`FW_MAIN_A` / `FW_MAIN_B` / `VBLOCK_A` / `VBLOCK_B` / `GBB rootkey` / `GBB
flags`. Keep `COREBOOT` and `RW_NVRAM` stock.

## Pre-flash checklist (run for EVERY image)

Use the futility tool we built in this repo (`vboot_reference/build/futility/futility`):

```
$ futility show IMAGE.bin
```

The output must include for both VBLOCK_A and VBLOCK_B:
- `Signature: valid` (keyblock signed by GBB rootkey)
- `Body verification succeeded.` (preamble's body_hash matches actual body)

If `Digest check failed` or `Body verification` is missing, the image will
fail vboot Phase 4 → recovery loop → all the painful states described above.
**Don't flash an image that fails this check.** This is the only mistake from
this session that I could and should have caught with pre-flight validation.

```
$ python3 -c "
import struct
d=open('IMAGE.bin','rb').read()
print('GBB flags: 0x{:08x}'.format(struct.unpack('<I', d[0x30100c:0x301010])[0]))
"
```

Verify GBB flags are intentional. Specifically:
- `FORCE_DEV_SWITCH_ON (0x08)`: needed to auto-enter dev mode for dev-signed
  RW. Trade-off: changes the recovery loop behavior in ways we don't fully
  understand. In this session, recovery loop with FORCE_DEV did NOT release
  the SPI bus reliably, while stock GBB (flags=0) did once.
- `DEV_SCREEN_SHORT_DELAY (0x01)`: cosmetic; no observed impact.
- **`DISABLE_FW_ROLLBACK_CHECK (0x20)`: AVOID THIS.** Including it makes
  the stock recovery loop iterate fast enough to saturate the SPI bus.

```
$ python3 -c "
import hashlib
img = open('IMAGE.bin','rb').read()
stock = open('/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin','rb').read()
assert hashlib.sha256(img[0:0x300000]).digest() == hashlib.sha256(stock[0:0x300000]).digest()
print('COREBOOT byte-identical to stock — OK')
"
```

This guarantees the COREBOOT invariant for the new image.

## Driver code rule (bounded retries)

Even with the above flash-side hygiene, a buggy RW driver can lock the SPI
bus indefinitely. Bound every hardware-touching retry loop and halt cleanly
when exhausted:

```c
#define MAX_RETRIES 3
static int retry_count, gave_up;
if (gave_up) return;
if (retry_count >= MAX_RETRIES) {
    printf("driver: giving up after %d attempts\n", retry_count);
    gave_up = 1;
    return;
}
retry_count++;
/* attempt; if it fails, the next poller invocation retries */
```

In practice this session this halt **did** trigger but **did not** restore
SuzyQ access — so don't rely on it alone. It still helps because it stops
adding to the SPI saturation.

## What we actually proved works

Across the 2026-05-28/29 session, exactly one SuzyQ flash succeeded reliably
in a known state:

1. Chip = stock (just restored via CH341A from `gale-spi-stock-2026-05-28.bin`).
2. UCSI CONNECTOR_RESET (full power cycle to the gale's hub).
3. `gale rec on; gale dev off`.
4. `gale power on`.
5. Wait ~18 seconds (AP UART showed coreboot through TZBSP + USB HOST1 init).
6. `gale power off` (via EC) then **immediate** `flashrom -p raiden_debug_spi -w IMG --fmap -i FW_MAIN_A`.

This wrote `FW_MAIN_A` (outside `WP_RO`) successfully. The same sequence with
the chip carrying dev-signed RW + GBB flags 0x09 (FORCE_DEV + SHORT_DELAY)
did not detect the chip — all subsequent attempts returned `RDID byte 0
parity violation. id1 0x00, id2 0x00`.

We could not in this session reproduce the working sequence after any other
flash operation. The original success was likely opportunistic on a specific
post-boot timing window that we don't fully understand. **Treat that one
success as anecdotal, not a recipe.**

## Robust SuzyQ recovery procedure (when it works)

For best chance of success when the chip is in a state where SuzyQ should
work (= stock or near-stock):

```python
# 1. Hard cycle via UCSI (cuts ALL power)
sudo sh -c 'echo 0x10003 > /sys/kernel/debug/usb/ucsi/USBC000:00/command'

# 2. Force recovery boot (recovery mode loads RO depthcharge, bypasses RW)
echo 'gale rec on' > <EC tty>
echo 'gale dev off' > <EC tty>
echo 'gale power on' > <EC tty>

# 3. Wait for recovery loop to start
sleep 22  # (or capture UART and wait for VbBootRecovery messages)

# 4. Atomic: power off AP, then flashrom (NO intervening commands)
echo 'gale power off' > <EC tty>
sleep 1.2
sudo flashrom -p raiden_debug_spi -c "W25Q64BV/W25Q64CV/W25Q64FV" \
    -w IMG --fmap -i REGION
```

For `WP_RO` regions (COREBOOT, FMAP, GBB), set `WP_L = 1` BEFORE the power
off transition: `echo 'gpioset WP_L 1' > <EC tty>` while the EC's rails are
still alive (the override persists across the power-off transition).

**If `flashrom` returns "No EEPROM/flash device found" with id1=0x00 id2=0x00,
SuzyQ is not viable for this chip state**. Don't keep cycling — give up,
acknowledge the emergency, and reach for the CH341A. Repeated SuzyQ attempts
on a contended bus risk additional chip damage (status register flips,
interrupted partial writes).

## CH341A recovery (the deterministic fallback)

When SuzyQ fails:

1. Power off the gale: physically unplug the USB-C cable from the laptop.
2. Clip the CH341A SOIC-8 onto U45 (W25Q64FV). **3.3 V only** — confirm the
   programmer's voltage jumper before clipping.
3. `lsusb` should show `1a86:5512`.
4. `sudo flashrom -p ch341a_spi --flash-name` should find the chip.
5. `sudo flashrom -p ch341a_spi -c "W25Q64BV/W25Q64CV/W25Q64FV" -w IMG`
6. Verify `VERIFIED.` appears.
7. Unclip, reconnect USB-C, boot.

In this session CH341A worked reliably every time (3 uses, all VERIFIED).
The first failed-erase-then-retry-with-different-erase-function recovery
that flashrom did automatically also worked. Treat CH341A as the
deterministic recovery, not as an emergency fallback.

## What I would do differently next time

1. **Lead with futility-verify** before flashing anything. The first emergency
   was a stale body_hash in the image that futility would have flagged.

2. **Stick with stock GBB (flags=0)** unless I genuinely need FORCE_DEV.
   The user-press-the-dev-button-once route is annoying but doesn't put the
   recovery loop into a busy state.

3. **Build the driver with the bounded-retry-and-halt code from day one**,
   not as a reaction to the first SPI lockup. Bounded retries are cheap and
   prevent the worst class of failure.

4. **Treat SuzyQ as opportunistic, not architectural.** Use it when it
   works, but don't rely on it for recovery. Plan CH341A access into the
   workflow.

5. **Probe the chip with flashrom every time you're in a known-good state.**
   This identifies any "lost SuzyQ access" emergency before doing further
   modifications.

## Open questions (things I didn't fully understand)

- Why does stock RO recovery loop release the SPI bus with stock GBB but
  not with our modified GBB (FORCE_DEV_SWITCH_ON + DEV_SCREEN_SHORT_DELAY)?
  The exact mechanism (vboot code path that differs) is unverified.

- Why does depthcharge's `halt()` not free the bus on this hardware? The
  IPQ's QUP master should idle. Empirically, post-halt flashrom still
  returns 0x00.

- Whether there's an EC command sequence we haven't found that ACTIVELY
  drives the bus mux for raiden_debug_spi to take over. We probed all EC
  commands (`flashwp`, `spixfer`, `syslock`, etc.) and didn't find one.

- Whether holding the AP in reset via some yet-undiscovered EC GPIO path
  (with VDD_3P3 alive) would give clean SuzyQ access. The IPQ's I/O pads
  on the SPI lines do something when CPU rail is off, and we couldn't
  isolate it without a scope.

These remain open. Future hardware-level diagnostics (scope traces of
SPI lines in various AP states) would resolve them.

## Recovery script inventory

- `tmp/ucsi_hardcycle.py` — software-controlled hard power cycle of the gale.
- `tmp/flash_rw.py` — SuzyQ-only RW flash (gale power off + atomic flashrom).
- `tmp/netboot_server.py` — DHCP+TFTP for `enx00e04c68016b` (10.42.1.1).
- `tmp/bringup.py` — UCSI cycle + power on + capture-and-gate-track.
- `tmp/test_t_a_to_f.py` — boot test + halt-fallback verification + post-halt
  SuzyQ probe.

`docs/ch341a-recovery.md` covers the CH341A procedure in detail.
`docs/bringup-log.md` is the running diary of what worked, what didn't,
and why.

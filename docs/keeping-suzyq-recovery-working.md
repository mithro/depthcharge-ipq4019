<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Keeping the Google Wifi (gale) puck always reflashable via SuzyQ

## TL;DR

SuzyQ flashing on the gale **works reliably**. The procedure is small and
already documented in `/home/tim/local/gwifi/gale-spi-flash-backup.md`:

```
echo "gale power off" > /dev/ttyUSB0           # EC console
sudo flashrom -p raiden_debug_spi -r dump.bin  # NO -c, NO target=, atomic
```

If SuzyQ "doesn't work" for you, the cause is almost always one of three
procedural mistakes documented below — not the device.

CH341A is the **emergency** fallback only. Reaching for the CH341A means you
broke something that the SuzyQ + EC bridge should have handled.

---

## Why this matters

The gale's SPI flash (Winbond W25Q64FV at U45) is the only path the device
boots from. The SuzyQ cable + EC's `raiden_debug_spi` bridge is the in-band,
no-disassembly way to read/write that chip. If you keep this path working,
you can iterate on firmware without ever opening the case. If you break it,
the only way back is a SOIC-8 clip + CH341A on the bare chip.

## The procedure (from `gale-spi-flash-backup.md`)

### Read

```bash
echo "gale power off" > /dev/ttyUSB0
sudo flashrom -p raiden_debug_spi -r dump.bin
```

### Write (whole chip)

```bash
echo "gale power off" > /dev/ttyUSB0
sudo flashrom -p raiden_debug_spi -w image.bin
```

### Write (single FMAP region — preferred for small diffs)

```bash
echo "gale power off" > /dev/ttyUSB0
sudo flashrom -p raiden_debug_spi -w image.bin --fmap -i FW_MAIN_A
```

### Write a WP_RO region (COREBOOT, FMAP, GBB) — deassert WP first

```bash
echo "gpioset WP_L 1"   > /dev/ttyUSB0   # deassert WP via EC
echo "gale power off"   > /dev/ttyUSB0
sudo flashrom -p raiden_debug_spi -w image.bin --fmap -i GBB
```

## The three procedural mistakes that make it look broken

### Mistake 1: passing `-c W25Q64BV/W25Q64CV/W25Q64FV` (or any `-c <chip>`)

The EC's raiden_debug_spi bridge does NOT surface a database-matched JEDEC
ID. The RDID (`0x9F`) response from the bridge is not a clean
manufacturer-and-device-ID. Flashrom must detect the chip via **SFDP** and
report it as `Unknown flash chip "SFDP-capable chip" (8192 kB, SPI)`.

With `-c`, flashrom insists on JEDEC ID matching, RDID returns garbage, and
you get:

> `RDID byte 0 parity violation. compare_id: id1 0x00, id2 0x00`
> `No EEPROM/flash device found.`

**Fix:** drop the `-c` flag entirely. Let flashrom autodetect via SFDP.

### Mistake 2: doing a separate `flashrom --flash-name` probe before the real operation

flashrom's raiden_debug_spi programmer re-enables AP power on exit (the
ENABLE control transfer's shutdown path drops the bridge and the EC's
default response brings the AP back). So:

```
gale power off
flashrom --flash-name           # AP off → probe OK, then AP re-powered on exit
flashrom -w image.bin           # ❌ AP is running; bus contended; write fails
```

**Fix:** never probe separately. Use one atomic flashrom invocation per
operation: `gale power off && flashrom -w image.bin`. If you want to verify
the chip is reachable, do it implicitly — let the write itself fail noisily
if it can't.

### Mistake 3: assuming `gale power off` synchronously kills the IPQ

`gale power off` from the EC is a sequenced power-down (CPU rail down,
I/O rails settle, flash rail stays up). A previously-running IPQ holds the
SPI bus until it is actually powered down. Issuing `gale power off`
immediately followed by a flashrom probe is fine — flashrom's USB control
transfer to the EC plus the EC's bridge takeover happen quickly enough that
the IPQ's pads have tristated by the time SPI clocks start. But:

```
flashrom (forces AP on)
gale power off                   # async; AP not actually idle yet
flashrom -w ...                  # ❌ races AP power-down
```

**Fix:** ensure each flashrom call is preceded by `gale power off` (not by a
prior flashrom call). One `gale power off` → one flashrom invocation.

## Empirical evidence (2026-05-29)

After the v3 image was flashed via CH341A and the device booted, the SuzyQ
read + region-verify confirmed:

| Region          | dump vs v3.bin | dump vs stock | notes                          |
|-----------------|----------------|---------------|--------------------------------|
| BOOT_STUB (3 MB)| match          | match         | COREBOOT pristine              |
| FMAP            | match          | match         |                                |
| GBB (256 KB)    | match          | differs       | dev rootkey replaces stock     |
| RW_SECTION_A    | match          | differs       | netboot RW                     |
| VBLOCK_A        | match          | differs       | dev-signed                     |
| FW_MAIN_A       | match          | differs       | netboot driver                 |
| VBLOCK_B        | match          | match         | unchanged                      |
| FW_MAIN_B       | differs        | differs       | boot modified Slot B           |
| RW_NVRAM        | match          | match         | empty                          |
| RW_VPD          | match          | match         |                                |
| RO_VPD          | match          | match         |                                |

That same session then wrote FW_MAIN_B back to v3 content via SuzyQ
(`flashrom -p raiden_debug_spi -w v3.bin --fmap -i FW_MAIN_B`) — 42 s,
exit=0, "Erase/write done." Confirms read AND write work end-to-end with
the correct procedure.

## Hardware facts (verified)

- EC firmware: `gale_v1.1.5337-0115719` (2016-10-03 build).
- USB interface map (subclass / iInterface):
  - if 0 (0xff/0x50): EC_PD console (`/dev/ttyUSB0`)
  - if 1 (0xff/0x50): AP console (`/dev/ttyUSB1`)
  - if 3 (0xff/0x51): raiden_debug_spi bridge (EP 0x83 IN / 0x03 OUT)
- Power rails the EC controls (verified with `gpioget`):
  - `SYS_PWR_EN` — master enable
  - `VDD_3P3_EN` — flash chip Vcc + AP I/O ring
  - `VDD_1P8_EN` — AP rail
  - `VDD_1P35_EN` — DDR rail
  - `VDD_1P1_CPU_EN` — IPQ CPU core
  - `WP_L` — chip WP pin (1 = deasserted = writable)
  - `VDD_3P3_2G_EN` — 2.4 GHz radio
- After `gale power on`: all of the above go to 1.
- After `gale power off` (from a running AP): CPU/1P8 drop to 0, **3P3 stays
  at 1** (flash remains powered for the EC bridge), SYS_PWR_EN stays 1.

## Pre-flash checklist (run for EVERY image)

```bash
$ ./vboot_reference/build/futility/futility show IMAGE.bin
```

For each VBLOCK: must show `Signature: valid` and `Body verification succeeded.`
If `Body verification` is missing (e.g. preamble has `USE_RO_NORMAL`),
re-sign with `futility sign --flags 0` so the body hash is recomputed.

```bash
$ python3 -c "
import struct, hashlib
d = open('IMAGE.bin', 'rb').read()
print('GBB flags: 0x{:08x}'.format(struct.unpack('<I', d[0x30100c:0x301010])[0]))
stock = open('/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin','rb').read()
assert hashlib.sha256(d[0:0x300000]).digest() == hashlib.sha256(stock[0:0x300000]).digest(), 'COREBOOT differs from stock!'
print('COREBOOT byte-identical to stock — OK')
"
```

Intentional GBB flags:
- `FORCE_DEV_SWITCH_ON (0x08)`: auto-enter dev mode for dev-signed RW. Safe.
- `DEV_SCREEN_SHORT_DELAY (0x01)`: cosmetic. Safe.
- `DISABLE_FW_ROLLBACK_CHECK (0x20)`: **avoid.** Speeds up recovery-loop
  iterations to the point where they hammer the SPI bus.

Keeping `COREBOOT` byte-identical to stock means the device can always
recovery-boot (`gale rec on`) into stock RO depthcharge, which periodically
yields the SPI bus to the EC bridge. This is your safety net.

## Driver code rule (bounded retries)

Even with the right flash procedure, an RW driver that loops forever on
hardware initialization can hold the SPI bus indefinitely while the AP is
powered. Bound every hardware-touching retry loop:

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
/* attempt; return on failure so the next poll retries */
```

This is good engineering hygiene — the driver halts cleanly rather than
spamming MDIO/PSGMII writes forever. It is **not** required for SuzyQ
recovery: `gale power off` powers down the AP regardless of what the
driver is doing, so the documented procedure works whether the driver
halts or not. Bounded retries just make the failure quieter (and the
iterate-flash-iterate loop shorter, since you don't have to wait for
the EC's `gale power off` to take effect against a busy AP).

## CH341A recovery (true emergency only)

You should never need this if rules above are followed. If you do:

1. Power off the gale: unplug USB-C from the laptop.
2. Clip CH341A SOIC-8 onto U45 (W25Q64FV). **3.3 V only** — verify the
   programmer's voltage jumper before clipping.
3. `lsusb` should show `1a86:5512`.
4. `sudo flashrom -p ch341a_spi --flash-name` finds the chip.
5. `sudo flashrom -p ch341a_spi -w IMG.bin`
6. Verify `VERIFIED.` then unclip and reconnect USB-C.

See `docs/ch341a-recovery.md` for the detailed step-by-step.

## What I would do differently next time

1. **Read `gale-spi-flash-backup.md` BEFORE writing my own SuzyQ scripts.**
   The procedure was always there. I wrote scripts that added unnecessary
   pre-flight probes (mistake 2) and the wrong `-c` flag (mistake 1), then
   blamed the architecture when they failed.
2. **Run `futility show` on every image before flashing.** A stale body_hash
   from a forgotten resign is recoverable via SuzyQ; reaching for CH341A
   first is overreaction.
3. **Bound every driver retry loop from day one.**
4. **When a procedure fails, suspect the procedure first.** "SuzyQ is
   broken" was the wrong root-cause; "I'm passing `-c` when I shouldn't"
   was the right one.

## Recovery script inventory

- `tmp/ucsi_hardcycle.py` — software-controlled hard power cycle (rarely
  needed for flashing; useful for recovering from a hung EC).
- `tmp/flash_rw.py` — SuzyQ-only RW flash (gale power off + atomic flashrom).
  Already correct.
- `tmp/correct_suzyq.py` — full-chip SuzyQ read with the correct procedure.
- `tmp/correct_suzyq_write.py` — full-region SuzyQ write with the correct
  procedure.
- `tmp/verify_regions.py` — region-by-region comparison of a SuzyQ dump
  against reference images.
- `tmp/netboot_server.py` — DHCP+TFTP on `enx00e04c68016b` (10.42.1.1).

`docs/ch341a-recovery.md` covers the emergency CH341A procedure.
`docs/bringup-log.md` is the running diary; the late-session "SuzyQ is
broken" conclusion in that file is wrong — see this document for the
correct picture.

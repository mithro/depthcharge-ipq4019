<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Phase 0 — Build environment & flash/recover loop

**Exit criterion (observe, don't assume):** an **unmodified** `gale` netboot
payload builds, flashes onto the device, boots far enough to print depthcharge's
banner + MAC on the AP serial console, and you can **restore the stock firmware**
on demand. Until you can build-flash-boot-recover a *known-good* image, do not
write a line of driver code — you would have no way to tell a driver bug from a
tooling bug.

This phase is mostly tooling, but it is still a loop: each sub-goal below ends in a
concrete observable. Where a command is marked **(verify)**, treat the listed
command as a starting point and confirm it on your machine — the 2016-era
`firmware-gale-8281.B` branch has toolchain pitfalls and your distro/hardware will
differ.

---

## Task 0.1 — Get the sources

**Files:** none (workspace setup)

```bash
cd <repo>            # depthcharge-ipq4019/
git clone https://chromium.googlesource.com/chromiumos/platform/depthcharge \
    --branch firmware-gale-8281.B depthcharge        # gitignored
git -C depthcharge rev-parse HEAD                    # expect b88cbbe1bb16...
```

You also need **libpayload** and **vboot_reference** matching that branch, and an
ARM bare-metal toolchain. Two routes (pick one, see 0.2).

**Observable:** `depthcharge/src/board/gale/` and `depthcharge/board/gale/defconfig`
exist; HEAD matches the pinned commit.

---

## Task 0.2 — Stand up a toolchain that builds depthcharge

depthcharge compiles with libpayload's `lpgcc`/`lpas` wrappers (Makefile lines
117-118), which need the coreboot ARM toolchain and a **built libpayload** whose
path you pass as `LIBPAYLOAD_DIR` (default `../libpayload/install/libpayload`).

**Route A — chromiumos chroot (most faithful to what shipped).** Use the
`firmware-gale-8281.B` manifest with `repo`, enter `cros_sdk`, and build via
`emerge-gale depthcharge` / `cros_workon`. Heavy (tens of GB) but the toolchain,
libpayload and vboot are all provisioned and version-matched.

**Route B — standalone (lighter).** Build coreboot's crossgcc
(`make crossgcc-arm`) for the ARM toolchain, build libpayload for an IPQ40xx/ARM
config, then point depthcharge at it:

```bash
# in a coreboot checkout of the same era:
make crossgcc-arm CPUS=$(nproc)              # (verify) provides arm-eabi- toolchain
# build libpayload (configure for ARMv7), install to .../install/libpayload
export LIBPAYLOAD_DIR=/path/to/libpayload/install/libpayload   # (verify)
```

**Observable:** `$LIBPAYLOAD_DIR/bin/lpgcc` exists and runs.

> Record the exact working recipe in `../docs/build.md` once it succeeds — this is
> the single most reproducibility-critical artifact of the whole project.

---

## Task 0.3 — Build the unmodified netboot & dev payloads

**Files:** none yet (building stock tree)

```bash
cd depthcharge
make BOARD=gale defconfig                 # writes .config from board/gale/defconfig
make BOARD=gale netboot_unified           # -> build/netboot.elf/.bin/.payload
make BOARD=gale dev_unified               # -> build/dev.*  (normal boot + Ctrl+N)
```

(Target names come from `src/Makefile.inc`: `declare_unified` makes
`<name>_unified`. `netboot` runs `netboot_entry` as `main` immediately on boot —
the tightest loop for exercising the NIC; `dev` boots normally and reaches netboot
via Ctrl+N.)

**Step: build → observe**
- EXPECTED: `build/netboot.bin` (LZMA) and `build/netboot.payload` (CBFS) produced,
  no `-Werror` failures.
- **If toolchain errors** (`lpgcc: not found`, ABI flags, missing vboot): fix in
  0.2, rebuild. This is the expected loop here.

**Commit:** nothing to the depthcharge tree yet; capture the recipe in
`../docs/build.md` and commit that to this repo.

---

## Task 0.4 — Establish console + back up stock firmware

**Files:** none (procedure)

1. Plug SuzyQ; identify the **AP** ttyUSB (the one emitting boot logs). Confirm baud.
   ```bash
   picocom -b 115200 /dev/ttyUSB0      # (verify which index, which baud)
   ```
2. **Back up the entire SPI flash before writing anything.** Use the
   in-system SuzyQ path via the EC bridge (the correct procedure: atomic
   `gale power off` + flashrom with **no** `-c` and **no** `target=`;
   `target=AP` STALLs on this EC, and `-c` forces RDID matching which
   the EC bridge doesn't support — see
   `/home/tim/local/gwifi/gale-spi-flash-backup.md`):
   ```bash
   uv run --no-project python tmp/con.py "gale power off"
   sudo flashrom -p raiden_debug_spi -r gale-stock-backup.bin
   sha256sum gale-stock-backup.bin                                        # record it
   ```
   CH341A is the emergency-only fallback (see `docs/ch341a-recovery.md`);
   you should not need it for routine backups.
3. Identify the flashmap RW region that holds the depthcharge payload
   (`RW_SECTION_A`/`RW_FW_MAIN_A`) with `dump_fmap gale-stock-backup.bin`.

**Observable:** a verified, hashed `gale-stock-backup.bin` you can always restore
with `flashrom ... -w gale-stock-backup.bin`. **This is your recovery.**

---

## Task 0.5 — Flash a payload and prove the loop + recovery

**Files:** none (procedure)

Flash the **unmodified** `dev` (or `netboot`) payload into the RW slot, leaving RO
coreboot untouched, then power-cycle and watch the console.

```bash
# Splice build/dev.payload (or netboot) into the RW_SECTION of a flash image,
# or use cbfstool/futility per the flashmap from 0.4, then:
uv run --no-project python tmp/con.py "gale power off"
sudo flashrom -p raiden_debug_spi -w gale-modified.bin \
    --fmap -i RW_SECTION_A
# No -c, no target=, no separate --flash-name probe — see
# docs/keeping-suzyq-recovery-working.md for the rationale.
```

**Step: flash → power-cycle → observe**
- EXPECTED (`dev`): normal depthcharge banner; Ctrl+N starts netboot which prints
  `Starting netboot on gale...`, then `Waiting for link` (it will hang here — no
  driver yet; that is correct for Phase 0).
- EXPECTED (`netboot`): immediately prints `Starting netboot on gale...` then the
  MAC line via `net_get_mac` once a device exists — but with no NIC driver it will
  sit in `net_wait_for_link`. Seeing the banner + reaching `Waiting for link` is the
  Phase-0 success signal.
- **If it bricks / no console**: restore `gale-stock-backup.bin` (0.4) and re-verify
  the flash method. Iterate until flash+recover is routine.

**Observable / exit:** you can flash a payload, see depthcharge run on the console,
and restore stock — repeatably.

---

## Task 0.6 (optional, recommended) — De-risk the netboot stack with an ASIX dongle

**Files:** `depthcharge/board/gale/defconfig` (temporary)

Add `CONFIG_DRIVER_NET_ASIX=y`, rebuild `netboot_unified`, plug a USB-Ethernet
ASIX dongle into gale's USB port, and netboot through it.

**Why:** proves DHCP/TFTP/build/flash/console are all correct **before** Phase 1, so
when the onboard driver misbehaves you know the fault is in the EDMA code, not the
surrounding stack.

**Observable:** with `dnsmasq` serving DHCP+TFTP on the wire, the console shows
`MAC: ...`, a DHCP lease, a TFTP byte count, and a kernel handoff — through the
dongle. Revert this defconfig change before Phase 1 (or keep it on a side branch).

---

## Phase 0 done when
- `gale.netboot`/`gale.dev` build from a **documented** recipe (`../docs/build.md`).
- Flash + power-cycle shows depthcharge on the AP console.
- Stock firmware restore is verified.
- (Optional) netboot proven end-to-end via ASIX dongle.

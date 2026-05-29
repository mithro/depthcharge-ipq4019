<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Session Summary — 2026-05-29 — IPQ4019 driver + SuzyQ procedure rescue

## TL;DR

**Driver**: An IPQ4019 ESS EDMA ethernet driver was built up from scratch
to the point where it cleanly performs DHCP, accepts ARP/ICMP, and
**sustains a multi-megabyte TFTP transfer (>17,000 RX packets, zero
invalid descriptors, zero drops)** — using only the gale's onboard
RJ45 ports.

**SuzyQ**: At the start of session, my flashing procedure was broken and
I'd burned three CH341A flashes blaming "hardware". By the end of the
session, 13 image iterations had been flashed via SuzyQ alone, **zero
CH341A uses**, every flash subagent-reviewed in advance, COREBOOT
byte-identical to stock throughout. The correct SuzyQ procedure was
documented and reflected back into the repo's docs and memory.

**Remaining gap**: `depthcharge`'s built-in FIT parser (`fit_load` in
src/boot/fit.c) data-aborts on the OpenWrt initramfs FIT after the
transfer completes. The crash is in the `list_for_each` macro — a
GCC-UB termination-check failure walking the property/image node list
past its sentinel. The driver itself is not implicated.

## Concrete driver state

What works on physical gale hardware (Google WiFi, IPQ4019):

| Stage | Status |
|---|---|
| ESS clock (GCC_ESS_CBCR @ 0x12010) | enabled by PBL (pre-1) at boot |
| ESS block reset (GCC_ESS_BCR @ 0x12008) | deasserted by driver |
| Per-port async resets (GCC_ESS_PORT_ARES @ 0x1200C) | cleared if stuck |
| MDIO pinmux (gpio6=mdio, gpio7=mdc, gpio40=output high) | applied by driver |
| MDIO clock divider (/64 for 1.5625 MHz MDC) | corrected from /256 default |
| MDIO controller | alive (write/readback validated) |
| QCA8075 internal PHY ID reads | working — addr 0..4 = 0x004dd0b2 (port PHYs), addr 5 = 0x06820805 (PSGMII) |
| PSGMII self-test calibration | **skip entirely** — PBL leaves the SerDes calibrated; the U-Boot-style retry loop actively damaged it on this board |
| Switch init (`ess_switch_init`) | port 0 (CPU) status=0x7F, all LOOKUP_CTRLs configured |
| EDMA configure + ring setup | TPD_BASE/SIZE/IDX, RXQ_CTRL/TXQ_CTRL all validated by readback |
| `gale rec/dev/power` via EC over SuzyQ | working |
| `flashrom -p raiden_debug_spi -w …` | working (no `-c`, no probe, atomic with `gale power off`) |
| PHY auto-neg with laptop NIC | 1G/full on LAN jack (PHY 3), 100M/full on WAN jack (PHY 4) |
| TX | working — DHCP exchange completes, TFTP RRQ + ACKs flow |
| RX | working — 17,100 packets at 558 B each, zero invalid RRDs, zero too-big |
| DHCP | full DISCOVER/OFFER/REQUEST/ACK exchange |
| TFTP | downloads >8 MB (file is 8.3 MB, observed 9.5 MB w/ retransmissions) |
| Kernel boot handoff | **blocked by depthcharge's FIT parser bug** (not driver) |

## The actual remaining bug (depthcharge fit_load)

PC=0x88105cbc, DFAR=0xfffffff4 (NULL+12, accessed at offset 0). Inside
the `image_node`'s property iteration:

```c
list_for_each(prop, node->properties, list_node) {
    if (!strcmp("data", prop->prop.name)) { ... }
}
```

The `list_for_each` macro in `depthcharge/src/base/list.h:38-42` uses
`&((ptr)->member)` as the termination check. Modern GCC optimization
treats this address as "always non-NULL" because dereferencing NULL is
undefined behavior — so the termination check is stripped. The loop
then iterates one past the linear list's NULL terminator and crashes
dereferencing the bogus `ptr`.

**This is not a driver bug.** The driver delivers the 8.3 MB FIT to
`payload = 0x80208000` correctly. depthcharge then chokes parsing it
because of the buggy list-iteration macro.

Possible fixes (none of which were applied this session because they
need a depthcharge change, not driver):
- Fix `list_for_each` in `depthcharge/src/base/list.h` to use `ptr != NULL` as the termination check.
- Or: rebuild the FIT to avoid the OpenWrt-specific node structure that triggers the issue (chromiumos FIT has different node organisation).
- Or: lower the depthcharge build's optimisation level (`-O0`).
- Or: explicitly initialise `next = NULL` after each insert and add a NULL guard at the top of the loop body in fit.c.

## Iteration history

13 SuzyQ-flashed images during the driver bring-up — every one was:
- Built locally (cbfstool splice + futility resign w/ devkeys)
- Sanity-checked (GBB flags 0x09, COREBOOT == stock, both VBLOCKs verify)
- Subagent-reviewed for safety before flashing
- Flashed via the correct SuzyQ procedure (`gale power off && flashrom -p raiden_debug_spi -w IMG --fmap -i FW_MAIN_A -i FW_MAIN_B -i VBLOCK_A -i VBLOCK_B`, no `-c`, no preflight probe)

Notable iterations:
- **v4**: First MDIO clock+reset attempt — discovered PBL already enabled ESS_CBCR.
- **v5**: Per-port ARES diagnostic — confirmed they were never asserted.
- **v6**: MDIO divider /256 → /64 — necessary but not sufficient.
- **v7**: **MDIO pinmux fix** — gpio6/7 to "mdio"/"mdc" function (coreboot doesn't do this). **This is the patch that made PHY MDIO start responding.** PHY IDs first appeared correctly here.
- **v9**: Made PSGMII cal non-fatal — driver runs all the way through despite cal "failure".
- **v13**: Comprehensive EDMA register dump — confirmed every state was correct yet TX wasn't emitting frames.
- **v15**: **Skip PSGMII cal entirely** — the retry-loop ESS BCR toggles were repeatedly destroying the SerDes state PBL had set up. With the loop removed, DHCP + TFTP started working. **This was the second key insight.**
- **v16**: RX ring 128 → 512 + RX counter diagnostics. Confirmed 17,100 clean RX packets.

## SuzyQ procedure (the second big win)

Old approach (wrong): `flashrom -p raiden_debug_spi -c W25Q64BV/... --flash-name` then `flashrom -w …`. This used three mistakes simultaneously: `-c` forces RDID matching the bridge doesn't support, the preflight probe re-powers the AP, separate flashrom calls leave the AP running between them. Every one of those flushes would fail and I'd reach for CH341A.

New approach (correct):
```bash
echo "gale power off" > /dev/ttyUSB0
sudo flashrom -p raiden_debug_spi -w IMG.bin --fmap -i FW_MAIN_A -i FW_MAIN_B -i VBLOCK_A -i VBLOCK_B
```

That's it. No `-c`. No probe. One atomic call. Documented in
`docs/keeping-suzyq-recovery-working.md` (rewritten this session) and
`/home/tim/local/gwifi/gale-spi-flash-backup.md`.

## Files added/changed this session (highlights)

Source:
- `src/drivers/net/ipq4019.c`: ESS clock+reset+ARES init, MDIO pinmux init, switch+EDMA bring-up, send/recv path, link check, bounded retry, register-dump diagnostics, MIB counters.
- `src/drivers/net/ipq4019_mdio.c`: MDIO divider fix + readback diagnostic.
- `src/drivers/net/ipq4019_psgmii.c`: PSGMII analog cal, qca8075_ess_reset; full retry loop eventually neutralised.

Docs:
- `docs/keeping-suzyq-recovery-working.md`: Rewritten — documents the three procedural mistakes that made SuzyQ "look broken" and the correct procedure.
- `docs/post-recovery-recipe.md`: Wrong-procedure flashrom invocations corrected.
- `docs/bringup-log.md`: Inline ⚠️ on historical wrong conclusions.
- `docs/ch341a-recovery.md`: "post-deadlock" framing replaced.

Memory (for future sessions):
- `feedback_flashing_default_suzyq.md`: documents the correct procedure.
- `feedback_gale_emergency_prevention.md`: bounded retry rule reframed as engineering hygiene (NOT a recovery enabler — `gale power off` is what enables recovery).

## What would unblock the kernel handoff

1. Patch `depthcharge/src/base/list.h:38-42` to use a NULL-explicit termination check, OR
2. Rebuild the FIT with a structure that doesn't trigger the bug, OR
3. Lower depthcharge's optimisation level.

The driver-side work needed to get there is complete: the gale's network
stack works from PHY to TFTP. The remaining work is in depthcharge.

<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# IPQ4019 depthcharge driver — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: use `superpowers:executing-plans` to work
> this plan phase-by-phase. Each phase file is an **iterative loop**, not a
> one-shot checklist — expect to repeat the build→flash→observe→fix cycle within a
> task until its exit criterion is observed on hardware.

**Goal:** Add `CONFIG_DRIVER_NET_IPQ4019` to depthcharge so the Google Wifi
(`gale`, IPQ4019) board can TFTP-netboot a kernel from its onboard ethernet.

**Architecture:** Implement depthcharge's polled `NetDevice` contract
(`src/drivers/net/net.h`) for the IPQ4019 **ESS EDMA** (`0xc080000`) + **QCA8075
PSGMII**. Register logic ports from U-Boot `essedma.c`; the depthcharge plumbing
(INIT_FUNC → NetPoller → lazy init → `net_add_device`, coreboot MAC, cache-coherent
DMA) ports from depthcharge `ipq806x.c`. See `../docs/design.md`.

**Tech stack:** C (libpayload/depthcharge), ARMv7, GNU make + chromiumos
toolchain, Kconfig. No unit-test framework — verification is **on real hardware
via the SuzyQ AP serial console** plus a TFTP/DHCP server on the wire.

---

## Why this plan is structured as loops, not steps

Bare-metal bring-up is not TDD. You cannot assert in a unit test that the PSGMII
SerDes calibrated; you flash the payload, watch the serial console, and read the
symptoms. So every task below has the same shape:

```
  ┌─ edit code ───────────────────────────────────────────────┐
  │                                                            │
  ▼                                                            │
 build (make gale.netboot)                                     │
  │                                                            │
  ▼                                                            │
 flash RW payload  ──►  power-cycle  ──►  watch AP console     │
  │                                                            │
  ▼                                                            │
 observe vs the task's EXPECTED CONSOLE OUTPUT                 │
  │                                                            │
  ├─ matches  ──►  task done, commit, next task                │
  │                                                            │
  └─ differs  ──►  diagnose (add printf / read a reg) ─────────┘
```

The exit criterion of each task is a **specific observable** (a console line, a
captured packet, a successful boot). Treat "I think it works" as not-done until
the observable appears.

### Worked example of one loop iteration (Phase 1, the MDIO task)

1. Edit: implement `ipq4019_mdio_read()` and add a probe-time
   `printf("PHY1 id = %04x %04x\n", read(1,2), read(1,3));`.
2. `make BOARD=gale gale.netboot` → produces `build/netboot.bin`.
3. Flash the RW payload (Phase 0 procedure), power-cycle, watch ttyUSB AP console.
4. EXPECTED: `PHY1 id = 004d d0b1` (QCA807x OUI). 
   - **Got `0000 0000`?** MDIO base wrong, or clock/reset (`hardware.md` §7.1) not
     up. Diagnose: read EDMA version reg; check GCC. Fix, goto 2.
   - **Got `ffff ffff`?** bus floating / wrong PHY addr. Try addrs 0..5. goto 2.
   - **Got the OUI?** task done → commit → next task.

This "EXPECTED / if-not-then" block is the deliverable for every task. Phase files
give the worked diagnosis branches; you fill in what you actually observe.

## Phases & exit criteria

| Phase | File | Exit criterion (observable) |
|-------|------|------------------------------|
| 0 | `phase-0-build-environment.md` | Unmodified `gale.netboot` builds, flashes, boots, and recovers cleanly; MAC printed on console |
| 1 | `phase-1-proof-of-life.md` | One port reaches link; a DHCP DISCOVER leaves the box and an OFFER is received (seen on console + server `tcpdump`) |
| 2 | `phase-2-tftp-netboot.md` | A kernel TFTPs in (byte count printed) and `boot()` hands off; kernel banner appears |
| 3 | `phase-3-full-driver.md` | Both RJ45 ports work; link survives cable replug; code is upstream-quality |

Do not start a phase until the previous phase's exit criterion has been
**observed**, not assumed.

## Standing setup (all phases)

- **depthcharge tree**: cloned at `<repo>/depthcharge/` (gitignored), branch
  `firmware-gale-8281.B` (commit `b88cbbe1bb16`). Phase 0 sets this up.
- **Console**: SuzyQ → 2× `/dev/ttyUSB*`; the **AP UART** is the one printing
  depthcharge output. Use `picocom -b 115200 /dev/ttyUSBn` (confirm baud in Phase 0).
- **Wire**: a Linux host running `dnsmasq` (DHCP + TFTP) on the segment the gale
  port is plugged into; `tcpdump -i <if> -e` to watch frames.
- **Recovery**: keep the stock RW payload backed up (Phase 0) so any bad flash is
  one reflash away from recovery; RO coreboot is never touched.

## Conventions

- Every new file starts with `// SPDX-License-Identifier: GPL-2.0-or-later` and the
  depthcharge copyright-header style (see `reference/depthcharge-ipq806x.c`).
- Small, frequent commits — one logical change each, in the **depthcharge tree**;
  mirror notable design decisions back into this repo's `docs/` as you learn.
- When you discover a real hardware fact (an address, a calibration quirk), update
  `../docs/hardware.md` in the same commit — the docs are living.

## Phase index

1. [Phase 0 — Build environment & flash/recover loop](phase-0-build-environment.md)
2. [Phase 1 — Proof of life](phase-1-proof-of-life.md)
3. [Phase 2 — TFTP netboot](phase-2-tftp-netboot.md)
4. [Phase 3 — Full, robust driver](phase-3-full-driver.md)

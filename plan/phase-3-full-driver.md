<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Phase 3 — Full, robust driver

**Exit criterion (observe):** netboot works from **either** physical RJ45 jack,
survives a cable unplug/replug and a warm reboot, and the code is clean enough to
propose upstream (SPDX, headers, checkpatch, no dead debug prints).

Phases 1–2 deliberately did "any one port, one clean pass." Phase 3 turns that into
a driver you'd trust and submit. Smaller, less risky tasks — but still the same
build→flash→observe loop, now with adversarial inputs (replug, both ports, reboot).

---

## Task 3.1 — Confirm and handle the real port topology

**Files:** `depthcharge/src/drivers/net/ipq4019.c`, `../docs/hardware.md` §2

Resolve which switch port/PHY each physical jack is (WAN=port 5, LAN=ports 1..4 per
`E:491-507`, but confirm gale's wiring from the coreboot gale DT / OpenWrt
`ipq40xx/chromium` google_wifi target). Make `ready()` report link if **any**
external jack is up, and select that port for traffic.

**Loop:** build → flash → boot; test each jack in turn.
- EXPECTED: link + netboot succeed regardless of which of the two jacks is cabled.
- **Commit:** "net: ipq4019: support both external ports; document topology".

---

## Task 3.2 — Robust link & speed/duplex

**Files:** `ipq4019.c`

Today the CPU port is forced 1000M/full (`E:528-535`) and that is fine for the
CPU↔switch link. Make the **external** link robust: read PHY speed/duplex after
autoneg and don't assume gigabit on the wire (a 100M switch/cable must still work).
Add a bounded wait for autoneg in `ready()` rather than a fixed delay.

**Loop:** build → flash → boot through a 100M switch and a 1G switch.
- EXPECTED: netboot works at both line rates; console reports the negotiated speed.
- **Commit:** "net: ipq4019: handle negotiated link speed/duplex".

---

## Task 3.3 — Clean teardown / `stop`

**Files:** `ipq4019.c`

Implement an orderly stop (`ipq40xx_edma_stop_rx_tx` `E:788-798` +
`ess_switch_disable_lookup`) and call it before `boot()` hands off, so the kernel's
own EDMA driver re-initializes from a known state (rings stopped, lookup disabled).

**Loop:** build → flash → boot → confirm the **kernel's** ethernet then comes up.
- EXPECTED: no wedged DMA / the in-kernel `ipqess` driver probes cleanly post-handoff.
- **Commit:** "net: ipq4019: stop EDMA/switch cleanly before kernel handoff".

---

## Task 3.4 — Adversarial robustness

**Files:** `ipq4019.c`

Exercise the failure paths the happy path skipped:
- Unplug the cable mid-`net_wait_for_link`, replug → must still link (don't latch a
  stale "ready").
- TX timeout path (`E:951-952`) and RX with no descriptors ready → must not hang or
  data-abort; return cleanly so uIP retries.
- Warm reboot (re-entry through `INIT_FUNC`) → re-init must be idempotent; the
  `static int initted` lazy-init must reset correctly per payload run.

**Loop:** build → flash → run each scenario.
- EXPECTED: every scenario recovers; no hang, no abort.
- **Commit:** "net: ipq4019: harden link/TX/RX error and re-init paths".

---

## Task 3.5 — Code quality & upstream readiness

**Files:** all new driver files; `../docs/*`

- SPDX `GPL-2.0-or-later` + depthcharge copyright header on every file; attribute the
  U-Boot/Linux origins of ported logic in comments.
- Remove bring-up `printf`s (or gate behind a debug flag); keep only useful info logs
  matching `ipq806x.c`'s verbosity.
- Run depthcharge's `.checkpatch.conf` / `PRESUBMIT.cfg` style checks.
- Confirm the production `depthcharge` payload still builds and is byte-unaffected
  (net code only links into `netboot`/`dev` — verify with a size diff).
- Update `../docs/design.md` and `../docs/hardware.md` to match the final code
  (resolved addresses, the real topology, any quirks found).

**Loop:** build all images; run checks.
- EXPECTED: clean checkpatch; `depthcharge` (non-net) payload size unchanged from a
  stock build; `netboot`/`dev` build and run.
- **Commit:** "net: ipq4019: finalize headers, logging, and docs".

---

## Task 3.6 (optional) — Upstream / write-up

If the goal includes giving this back: prepare a Gerrit change for
`chromiumos/platform/depthcharge` (or a fork/PR), referencing the U-Boot `essedma`
provenance, and write a short bring-up note (what coreboot already did vs. what the
driver does, the PSGMII calibration gotchas) for the next person.

---

## Phase 3 done when
- Netboot works from either jack, at 100M and 1G, across replug and warm reboot.
- Clean teardown lets the kernel's NIC driver take over.
- Code passes style checks and carries correct license/attribution.
- Production boot path is provably unaffected.
- Docs reflect reality.

<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Phase 2 — TFTP netboot

**Exit criterion (observe):** the gale netboot payload downloads a kernel over TFTP
(`The bootfile was N bytes long.` on the console) and `boot()` hands off — the
booted kernel's own banner appears on the AP console.

By Phase 1, DHCP and single-packet RX/TX work. The new stress in Phase 2 is a
**sustained, multi-megabyte TFTP transfer**: hundreds of back-to-back packets,
RFD-ring wraparound, and zero tolerance for a dropped/garbled frame (TFTP is
lock-step but a corrupt block stalls or corrupts the image). Most of this phase is
the same loop applied to *throughput* bugs.

The flow itself is already implemented in `depthcharge/src/netboot/netboot.c`
(`netboot()` → `net_wait_for_link` → `try_dhcp` → `tftp_read` → `boot`). You are
feeding it a working `NetDevice`, not writing new flow.

---

## Task 2.1 — Serve a real gale kernel over TFTP

**Files:** none (server side)

Configure `dnsmasq` on the wire to hand gale a TFTP server + bootfile, and place a
**gale-compatible kernel FIT image** in the TFTP root. The simplest valid payload is
a kernel built for `google,gale` / `google,gale-v2` (the compat strings in
`src/board/gale/board.c:76,81`); for first light even a kernel that just prints to
the same UART and halts is enough to prove the handoff.

```
# dnsmasq.conf (sketch)
dhcp-range=192.168.50.50,192.168.50.150,12h
dhcp-boot=vmlinux.fit            # -> becomes the DHCP "bootfile"
enable-tftp
tftp-root=/srv/tftp
```

netboot picks up the TFTP server IP and bootfile **from DHCP** when not predefined
(`netboot.c:124-139`), so no on-flash netboot params are required for manual bring-up.

**Observable:** `tcpdump` shows the OFFER carrying `siaddr`/`file`.

---

## Task 2.2 — First full transfer; measure where it breaks

**Files:** `depthcharge/src/drivers/net/ipq4019.c` (only if fixes needed)

**Loop:** build → flash → boot, cable in a working port, watch console + server.
- EXPECTED (success): `Bootfile supplied by DHCP server: ...`, a pause while blocks
  transfer, then `The bootfile was N bytes long.`
- EXPECTED (first attempt may fail): `Tftp failed.` or a stall. That is the start of
  the tuning loop, not a dead end.

---

## Task 2.3 — Tune the RX path for sustained load (iterate)

The likely failure modes and where to look:

- **Transfer stalls after K blocks** → RFD ring wraparound bug. Re-check the
  producer/consumer index math at the `count` boundary (`E:838-851`) and that every
  consumed RFD is recycled with its buffer re-armed.
- **Intermittent corrupt block / wrong length** → cache coherency. Ensure each RX
  buffer is `dcache_invalidate_by_mva` **before** reading the RRD/payload, and that
  RX buffers are cache-line aligned and sized so adjacent buffers don't share a line.
- **`recv` returns stale data** → you read the buffer before checking
  `rrd7 & EDMA_RRD7_DESC_VALID`, or didn't invalidate after DMA.
- **Occasional dropped frame under burst** → too few RFDs; raise the RX ring count;
  confirm RXQ enable + FIFO threshold (`E:772-779`).

Each fix is one loop iteration with the same observable: a *complete* `N bytes long`
that matches the file size on the server (`ls -l /srv/tftp/vmlinux.fit`).

**Commit** each distinct fix separately (e.g. "net: ipq4019: fix RFD ring wrap on
sustained RX").

---

## Task 2.4 — Boot handoff

**Files:** none (verification)

Once the byte count is correct and matches the server file, depthcharge calls
`boot()` with the downloaded FIT.

**Loop:** build → flash → boot.
- EXPECTED: after `The command line is: ...`, control transfers to the kernel and the
  **kernel's** early console output appears on the same AP UART.
- **If handoff hangs**: that's a kernel/FIT/cmdline issue (load address, FDT), not the
  NIC — your driver's job ended at a correct download. Sanity-check by diffing the
  downloaded image against the server copy (e.g. add a CRC print) to confirm the NIC
  delivered it intact.

---

## Phase 2 done when
- A multi-MB kernel TFTPs in with a byte count matching the server file, repeatably
  across several boots.
- `boot()` hands off and the kernel starts.
- This works via the `netboot` image (boots straight into netboot) **and** via the
  `dev` image's Ctrl+N path.

<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Phase 1 — Proof of life

**Exit criterion (observe):** with a DHCP/TFTP server on the wire and one gale RJ45
port cabled to it, the AP console shows link coming up, prints the MAC, transmits a
DHCP DISCOVER, and **receives an OFFER** (confirm with `tcpdump -e` on the server).
That single round-trip proves init + PSGMII + switch + MDIO + TX + RX all work.

Reference the vendored files throughout:
`reference/uboot-essedma.c` (`E:`), `reference/uboot-essedma.h` (`EH:`),
`reference/uboot-mdio-ipq4019.c` (`M:`), `reference/depthcharge-ipq806x.c` (`D:`).
Addresses/recipe: `../docs/hardware.md`.

Each task is the standard loop (`plan/README.md`): edit → `make BOARD=gale
netboot_unified` → flash RW → power-cycle → read console → match EXPECTED or
diagnose. Commit to the **depthcharge tree** after each green task.

---

## Task 1.1 — Wire up an empty driver that registers itself

Get the build system to compile and run a stub so the loop is tight before any
hardware code.

**Files:**
- Create: `depthcharge/src/drivers/net/ipq4019.c`
- Modify: `depthcharge/src/drivers/net/Kconfig`
- Modify: `depthcharge/src/drivers/net/Makefile.inc`
- Modify: `depthcharge/board/gale/defconfig`

**Kconfig** — add after `DRIVER_NET_IPQ806X`:
```kconfig
config DRIVER_NET_IPQ4019
	bool "IPQ4019 ESS EDMA ethernet controller"
	default n
```

**Makefile.inc** — add:
```make
net-$(CONFIG_DRIVER_NET_IPQ4019) += ipq4019.c
net-$(CONFIG_DRIVER_NET_IPQ4019) += ipq4019_mdio.c
net-$(CONFIG_DRIVER_NET_IPQ4019) += ipq4019_psgmii.c
```

**defconfig** — add `CONFIG_DRIVER_NET_IPQ4019=y`.

**ipq4019.c** (stub — copy the registration shape from `D:898-916`):
```c
// SPDX-License-Identifier: GPL-2.0-or-later
/* Copyright ... (depthcharge header style) */
#include <libpayload.h>
#include "base/init_funcs.h"
#include "drivers/net/net.h"

static void ipq4019_net_poller(struct NetPoller *poller)
{
	static int initted;
	if (!initted) {
		printf("ipq4019: net poller fired\n");   /* proof the hook runs */
		initted = 1;
	}
}
static NetPoller net_poller = { .poll = ipq4019_net_poller };

static int ipq4019_eth_driver_register(void)
{
	list_insert_after(&net_poller.list_node, &net_pollers);
	return 0;
}
INIT_FUNC(ipq4019_eth_driver_register);
```

**Loop:** build `netboot_unified` → flash → boot.
- EXPECTED: `netboot` reaches `Waiting for link` and the console prints
  `ipq4019: net poller fired` (proves `INIT_FUNC` ran and `net_wait_for_link` polls it).
- If absent: confirm `CONFIG_DRIVER_NET_IPQ4019=y` survived `defconfig` and the file
  built (grep the build log).

**Commit:** "net: ipq4019: register empty NetPoller stub".

---

## Task 1.2 — Port the register map (`ipq4019.h`)

**Files:** Create `depthcharge/src/drivers/net/ipq4019.h`

Port `EH:` wholesale: the `EDMA_REG_*`, `ESS_*`, `QCA807X_*`, `PSGMIIPHY_*`
#defines and the `edma_tpd` / `edma_rrd` / `edma_rfd` structs. Add depthcharge-side
base-address #defines from `../docs/hardware.md` §1:
```c
#define IPQ4019_EDMA_BASE	0x0c080000
#define IPQ4019_ESS_BASE	0x0c000000
#define IPQ4019_PSGMII_BASE	0x00098000
#define IPQ4019_MDIO_BASE	0x00090000
#define RGMII_TCSR_ESS_CFG	0x01953000
```
Drop U-Boot `GENMASK`/`BIT` only if libpayload lacks them — it has `<linux/bitops.h>`-style
helpers; otherwise keep using them.

**Loop:** `make` (compile only).
- EXPECTED: compiles clean.
- **Commit:** "net: ipq4019: add EDMA/PSGMII/switch register definitions".

---

## Task 1.3 — MDIO + MMD helpers (`ipq4019_mdio.c`)

The single most useful early diagnostic: read a PHY ID. Port `M:` (clause-22) and
add clause-45-indirect (MMD) helpers the PSGMII code needs.

**Files:** Create `depthcharge/src/drivers/net/ipq4019_mdio.c` (+ prototypes in `ipq4019.h`)

Strip U-Boot's DM: hardcode `IPQ4019_MDIO_BASE`, replace `readl_poll_sleep_timeout`
with a `udelay` poll loop (see `M:41-48`). Core read (from `M:50-72`):
```c
int ipq4019_mdio_read(uint8_t phy, uint8_t reg, uint16_t *val)
{
	void *b = (void *)IPQ4019_MDIO_BASE;
	if (mdio_wait_busy(b)) return -1;
	writel((phy << 8) | reg, b + 0x44);            /* MDIO_ADDR_REG */
	writel((1<<8) | 0 /*READ*/, b + 0x50);         /* MDIO_CMD_REG  */
	if (mdio_wait_busy(b)) return -1;
	*val = readl(b + 0x4c);                         /* MDIO_DATA_READ */
	return 0;
}
```
`ipq4019_mdio_write` mirrors it (`M:74-100`). In `probe`/init, clear bit 8 of
`MDIO_MODE_REG (0x40)` for clause-22 (`M:124-127`).

**MMD helpers** (clause-45-indirect via regs 0x0d/0x0e), needed by `psgmii_*`:
```c
/* devad = MDIO_MMD_AN(7) / MDIO_MMD_PMAPMD(1), etc. */
uint16_t phy_read_mmd(uint8_t phy, uint8_t devad, uint16_t reg) {
	ipq4019_mdio_write(phy, 0x0d, devad);          /* MMD ctrl: address */
	ipq4019_mdio_write(phy, 0x0e, reg);            /* MMD data: the reg  */
	ipq4019_mdio_write(phy, 0x0d, 0x4000 | devad); /* ctrl: data, no post-inc */
	uint16_t v; ipq4019_mdio_read(phy, 0x0e, &v); return v;
}
/* phy_write_mmd analogous, final step writes 0x0e */
```

Add a probe-time diagnostic: `printf("PHY%d id=%04x%04x\n", a, rd(a,2), rd(a,3))`
for `a` in 0..5.

**Loop:** build → flash → boot. (This is the worked example in `plan/README.md`.)
- EXPECTED: at least the port PHYs report a QCA OUI (`004d dxxx`), and addr 5 (PSGMII)
  responds. `0000`/`ffff` → see README diagnosis (clock/reset or wrong base/addr).
- **Commit:** "net: ipq4019: add MDIO clause-22 + MMD helpers".

---

## Task 1.4 — Clock/reset & EDMA reachability (resolve hardware.md §7.1)

Before ring setup, confirm the EDMA block is clocked and out of reset.

**Files:** `ipq4019.c` (init path)

Add an early read of an EDMA identity/control reg and print it. If MDIO already
worked in 1.3 (MDIO sits in the same ESS clock domain), the clock is likely on — but
confirm EDMA specifically. If reads are `0`/bus-fault, port U-Boot's clk/reset
(`E:1093-1105`, `ess_reset` `E:86-95`) as **direct GCC register pokes** (find the GCC
base + `GCC_ESS_CLK`/`ESS_RESET` bits for IPQ4019; cross-check coreboot gale).

**Loop:** build → flash → boot.
- EXPECTED: EDMA reg read returns a stable, non-fault value; no data-abort on console.
- **If data-abort/`0`**: implement clk enable + `ess_reset` (assert 10 ms, deassert
  10 ms), retry. Record the verdict in `../docs/hardware.md` §7.1.
- **Commit:** "net: ipq4019: ensure ESS clock/reset before register access".

---

## Task 1.5 — PSGMII calibration & self-test (`ipq4019_psgmii.c`) — THE RISK

Port the PSGMII bring-up faithfully (decision made). Expect the most loop
iterations here. Keep it isolated in its own file.

**Files:** Create `depthcharge/src/drivers/net/ipq4019_psgmii.c`

Port, in order, from `E:`:
1. The analog cal writes to `IPQ4019_PSGMII_BASE` (`E:1120-1130`): PLL_VCO,
   VCO_CALIBRATION_1 = `0x4ada`, wait 10 ms, = `0xada`.
2. `qca8075_ess_reset()` (`E:97-149`) — the BMCR `0x005b/0x001b/0x005b` dance,
   poll PHY MMD-PMAPMD `0x28` bit0, poll `psgmii_base+0xa0` bit0, RX-CDR
   freeze/release (`0x1a`=`0x2230`/`0x3230`).
3. The self-test (`E:151-438`): `psgmii_st_phy_prepare`, the ≤20-retry loop calling
   `qca8075_ess_reset` + switch-port loopback + serial test + parallel test +
   `psgmii_st_update_stats`, then per-PHY recover.

Deltas: PHYs are plain MDIO addresses (0..4 ports, 5 = PSGMII), not `phy_device*`;
replace `phy_read/write[_mmd]` with the 1.3 helpers; `get_timer`/`mdelay`/`udelay`
exist in libpayload. Switch-loopback helpers (`esw_port_loopback_set*` `E:65-84`)
poke `ESS_PORT_LOOKUP_CTRL`.

**Loop:** build → flash → boot. Add prints for each calibration gate.
- EXPECTED: `PSGMII PLL_VCO_CALIB` ready bits set (no "Not Ready" prints), and the
  self-test reports `succeed >= 1`. A single clean pass is enough for Phase 1.
- **If "Not Ready" / self-test never succeeds**: this is the classic SerDes flake.
  Verify the analog cal values went to the right base; verify all 5 port PHYs were
  prepared; bump retry count; compare register-by-register against `E:` and the Linux
  `ar40xx` calibration. Loop here patiently — the self-test exists precisely to make
  link reliable.
- **Commit:** "net: ipq4019: port QCA8075 PSGMII calibration and self-test".

---

## Task 1.6 — Switch init + EDMA rings + configure

**Files:** `ipq4019.c`

Port `ess_switch_init` (`E:520-580`), ring alloc (`E:987-1030`, use
`xmemalign(get_cache_line_size(), ...)` per `D:215-232`), `ipq40xx_edma_configure`
(`E:746-786`), `ipq40xx_edma_init_desc` (`E:673-728`), and
`ess_switch_disable_lookup` (`E:440-477`). Allocate the RX packet buffers
(`net_rx_packets[]` pattern, `D:25` + `D:234-268`).

**Loop:** build → flash → boot.
- EXPECTED: init runs to completion, no hang, no data-abort; optional debug print of
  TXQ/RXQ control regs shows the configured values.
- **Commit:** "net: ipq4019: switch init and EDMA ring/descriptor setup".

---

## Task 1.7 — `ready()` + `get_mac()`; reach link

Wire the `NetDevice`: lazy-init on first `ready()` (mirror `D:84-100` /
`ipq_net_poller` `D:898-903`), do the full 1.4–1.6 bring-up once, then report PHY
link. Reuse `D:40-75` `get_eth_mac_address` **verbatim** for `get_mac`.

**Files:** `ipq4019.c` (+ `net_add_device`, set `dev->ready/recv/send/get_mac`)

`ready()` returns link on any external port (PHY specific reg `0x11` bit10,
`EH:64-65`).

**Loop:** build → flash → boot with a cable in one port.
- EXPECTED: `net_wait_for_link` prints `done.` and returns; MAC prints via
  `try_dhcp`'s `net_get_mac` (`netboot.c:90-96`).
- **If never links**: check which port the cable is in vs the topology
  (`hardware.md` §2); try each RJ45; confirm switch lookup/MAC enable.
- **Commit:** "net: ipq4019: implement ready()/get_mac() and register NetDevice".

---

## Task 1.8 — `send()` + `recv()`; DHCP round-trip (EXIT)

Port `ipq40xx_eth_send` (`E:880-959`, keep the **4-TPDs-per-packet** trick and the
`flush_dcache_range`→`dcache_clean_invalidate_by_mva` mapping) and merge
`ipq40xx_eth_recv`+`free_pkt` (`E:800-854`) into one **copying** `recv` that obeys
depthcharge's `(buf,*len,maxlen)` signature (model the copy on `D:421-487`):
read RFD consumer idx; if `rrd7 & EDMA_RRD7_DESC_VALID`, copy `rrd6` bytes from past
the 16-byte RRD into `buf` (bounded by `maxlen`), then recycle the RFD and advance.

**Loop:** build → flash → boot, with `dnsmasq` (DHCP+TFTP) on the wire and
`tcpdump -i <if> -e -n port 67 or port 68` on the server.
- EXPECTED: console prints the MAC, then DHCP succeeds — `My ip is X`, `DHCP server ip
  is Y` (`netboot.c:104-108`). `tcpdump` shows DISCOVER from gale's MAC and an OFFER back.
- **If DISCOVER never appears**: TX path — check TPD producer idx advance and the
  cons==prod poll (`E:937-949`); verify cache flush of packet + descriptors.
- **If DISCOVER appears but no OFFER processed**: RX path — check RFD consumer idx,
  `rrd7` valid bit, the RRD/length offset, and the invalidate before reading the buffer.
- **Commit:** "net: ipq4019: implement send()/recv(); DHCP round-trip works".

---

## Phase 1 done when
- Console shows link, MAC, DISCOVER out, OFFER in, on at least one port.
- The full bring-up (clk/reset → MDIO → PSGMII self-test → switch → EDMA) runs
  reliably across several power cycles (not a one-off fluke).
- `../docs/hardware.md` open items §7.1–§7.3 are resolved with observed facts.

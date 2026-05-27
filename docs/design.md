<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Design: depthcharge IPQ4019 ethernet driver

This is the architecture. For concrete register addresses see `hardware.md`; for
the step-by-step task breakdown see `plan/`.

## 1. Goal

Add `CONFIG_DRIVER_NET_IPQ4019` to depthcharge so the **`gale`** board (Google
Wifi, IPQ4019) can **TFTP-netboot a kernel** from its **onboard** ethernet, using
depthcharge's existing `netboot`/`dev` payloads. Reaching that is staged:
**proof-of-life → netboot → full driver** (phases in `plan/`).

## 2. The core idea

depthcharge's network driver interface (`src/drivers/net/net.h`) is a small,
**polled** contract:

```c
typedef struct NetDevice {
    ListNode list_node;
    int (*ready)(struct NetDevice *dev, int *ready);          // link up?
    int (*recv)(struct NetDevice *dev, void *buf, uint16_t *len, int maxlen);
    int (*send)(struct NetDevice *dev, void *buf, uint16_t len);
    int (*mdio_read)(struct NetDevice *dev, uint8_t loc, uint16_t *val);   // optional
    int (*mdio_write)(struct NetDevice *dev, uint8_t loc, uint16_t val);   // optional
    const uip_eth_addr *(*get_mac)(struct NetDevice *dev);
    void *dev_data;
} NetDevice;
```

`net_add_device()` asserts only `ready`, `recv`, `send`, `get_mac` — `mdio_*` are
optional (the existing ipq806x driver leaves them NULL and uses its own internal
MDIO). There are **no interrupts**: `net.c` busy-polls `ready()` until link, then
`net_poll()` pumps `recv()`→uIP→`send()`.

We have two upstream drivers that, *together*, make implementing this contract
straightforward:

- **U-Boot `essedma.c`** gives the **register-correct, polled, bare-metal** logic
  for *this exact MAC* (IPQ4019 ESS EDMA + QCA8075 PSGMII). Its `eth_ops`
  (`start`/`send`/`recv`/`free_pkt`/`stop`) are already a polled model.
- **depthcharge `ipq806x.c`** gives the **structural** template for how a Qualcomm
  NIC plugs into depthcharge: `INIT_FUNC` → `NetPoller` → lazy hardware init on
  first poll → `net_add_device()`, plus coreboot MAC handling and ARM
  cache-coherent DMA helpers.

So: **take the shape from `ipq806x.c`, take the registers from `essedma.c`.**

## 3. Operation mapping (U-Boot → depthcharge)

| depthcharge `NetDevice` op | U-Boot `essedma.c` source | Port notes |
|---|---|---|
| registration (`INIT_FUNC`) | `U_BOOT_DRIVER`/probe | replace DM with `INIT_FUNC`+`NetPoller` (copy ipq806x.c shape) |
| one-time init (lazy, in `ready`) | `essedma_probe`+`edma_init` | the §3 recipe in `hardware.md` |
| `ready(dev,*ready)` | `psgmii_st_phy_link_is_up` / PHY specific reg 0x11 bit10 | also triggers lazy init the first time (like `ipq_phy_check_link`) |
| `send(dev,buf,len)` | `ipq40xx_eth_send` | fill 4 TPDs, bump TPD prod idx, poll until cons==prod |
| `recv(dev,buf,*len,max)` | `ipq40xx_eth_recv` + `ipq40xx_eth_free_pkt` | read RFD cons idx; if `rrd7&0x8000`, copy `rrd6` bytes past the 16-byte RRD; recycle RFD |
| `get_mac(dev)` | `write_hwaddr` (inverse) | reuse ipq806x.c's `get_eth_mac_address` verbatim (`lib_sysinfo.macs[0]` + QFPROM SHA1 fallback) |
| `mdio_read/write` | (phylib) | leave NULL on `NetDevice`; implement internal MDIO from `mdio-ipq4019.c` |

`recv` semantic difference to respect: U-Boot returns a *pointer* into the RX
buffer and frees later; depthcharge's `recv` must **copy** `len` bytes into the
caller's `buf` (bounded by `maxlen`), exactly as `ipq806x.c`'s `ipq_eth_recv`
does. So merge U-Boot's `eth_recv`+`free_pkt` into one copying `recv`.

## 4. Files

**New** (under depthcharge `src/drivers/net/`):

```
ipq4019.c        # the NetDevice driver: registration, lazy init, send/recv/ready/get_mac,
                 #   EDMA ring setup, ess switch init  (port of essedma.c)
ipq4019.h        # register map + descriptor structs (port of essedma.h)
ipq4019_mdio.c   # clause-22 MDIO + clause-45 MMD helpers (port of mdio-ipq4019.c)
ipq4019_psgmii.c # QCA8075 PSGMII calibration / self-test (port of the psgmii_* fns)
```

Splitting PSGMII into its own file keeps the riskiest, most-likely-to-be-iterated
code isolated. (Merge back later if it stays small.)

**Edited**:

- `src/drivers/net/Kconfig` — add `config DRIVER_NET_IPQ4019`.
- `src/drivers/net/Makefile.inc` — `net-$(CONFIG_DRIVER_NET_IPQ4019) += ipq4019.c ipq4019_mdio.c ipq4019_psgmii.c`.
- `board/gale/defconfig` — add `CONFIG_DRIVER_NET_IPQ4019=y`.
- `src/board/gale/board.c` — only if the driver needs a board hook (e.g. a
  `board_wan_port_number()` analogue). The storm/ipq806x integration shows the
  board and driver are otherwise **decoupled**: the driver self-registers via
  `INIT_FUNC`; `board_setup()` is untouched.

No changes to `src/net/` (uIP) or `src/netboot/` — the new driver is consumed
through the existing `NetDevice`/`net_*` framework.

## 5. Porting deltas (U-Boot idioms → depthcharge/libpayload)

| U-Boot | depthcharge / libpayload |
|---|---|
| driver model (`udevice`, `dev_get_priv`, `U_BOOT_DRIVER`) | drop; use a static `IpqEthDev`-style priv + `INIT_FUNC` (see ipq806x.c) |
| OF/DT (`dev_read_addr_name`, `ofnode_*`, phy-handle) | drop; **hardcode** base addrs (`hardware.md` §1) + PHY addresses |
| `clk`/`reset` framework | check coreboot; else poke GCC directly (`hardware.md` §7.1) |
| phylib (`phy_read/write`, `phy_*_mmd`, `phy_device`) | minimal local MDIO + MMD helpers (port of `mdio-ipq4019.c`); represent PHYs as plain MDIO addresses |
| `flush_dcache_range(start,end)` | `dcache_clean_invalidate_by_mva(addr,len)` |
| `invalidate_dcache_range(start,end)` | `dcache_invalidate_by_mva(addr,len)` |
| `memalign(CONFIG_SYS_CACHELINE_SIZE,..)` | `xmemalign(get_cache_line_size(),..)` (as ipq806x.c) |
| `virt_to_phys` | `virt_to_phys` (libpayload provides it; ipq806x.c uses it) |
| `get_timer`/`mdelay`/`udelay` | same in libpayload |
| `printf`/`dev_dbg` | `printf` |

## 6. Build & image integration

depthcharge builds several payloads (`src/Makefile.inc`). Net drivers
(`net-objs`) are linked **only** into:

- **`netboot`** — standalone TFTP-netboot payload (`netboot_entry` is `main`).
- **`dev`** — developer image (normal boot **+** Ctrl+N netboot).

The normal verified-boot `depthcharge` payload does **not** include net code, so
this driver adds **zero size/risk to the production boot path**. Build with e.g.
`make BOARD=gale ... gale.netboot` (exact invocation pinned in `plan/phase-0`).

## 7. Verification strategy

The device is headless; the **SuzyQ serial console (AP UART)** is the instrument.
Each phase has explicit, observable exit criteria (see `plan/`), e.g.:

- Phase 1: console prints "link up", a DHCP DISCOVER is transmitted and an OFFER is
  received (watch with `tcpdump` on the server side too).
- Phase 2: `tftp_read` reports the kernel byte count and `boot()` hands off.

Because there is no production-path impact and the `netboot`/`dev` images live in
the RW payload, the build→flash→observe loop is recoverable (RO coreboot +
recovery image remain intact). `plan/phase-0` establishes the safe reflash/recover
cycle **before** any driver code is written.

## 8. Risks (ranked)

1. **PSGMII calibration** — port `psgmii_self_test()` faithfully (decision made);
   needs MMD MDIO helpers; expect on-device iteration. Isolated in `ipq4019_psgmii.c`.
2. **Clock/reset ownership** vs coreboot (`hardware.md` §7.1) — unblock early in Phase 1.
3. **Cache coherency** — descriptor flush granularity; keep the 4-TPD trick.
4. **gale port topology** — confirm RJ45↔port/PHY before Phase 3.

## 9. Alternative considered (and kept as a fallback)

**USB-Ethernet dongle via existing `DRIVER_NET_ASIX`.** gale has a USB host
(`new_usb_hc(XHCI, 0x8A00000)`), so enabling the existing ASIX driver needs almost
no new code and would prove the *netboot stack itself* end-to-end. It does **not**
satisfy the goal (onboard ports), but `plan/phase-0` uses it optionally to
de-risk: it separates "is my netboot/TFTP/build/flash loop correct?" from "is my
EDMA driver correct?" so Phase 1 debugging is about the MAC alone.

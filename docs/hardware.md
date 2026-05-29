<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# IPQ4019 ethernet hardware reference

Everything here is cross-checked against U-Boot `essedma.c`/`essedma.h`
(`reference/uboot-*`), the OpenWrt IPQ4019 device trees, and gale's own
device-tree fixup in depthcharge `src/board/gale/board.c`. Verify each address
against the coreboot gale memory map before trusting it in code.

## 1. The blocks and their base addresses

The IPQ4019 ethernet is **not** a discrete NIC — it is the SoC's integrated
**ESS (Ethernet SubSystem)**: an **EDMA** (Ethernet DMA) engine on the CPU side,
a 6-port wire-speed **switch**, and an internal **QCA8075 PSGMII** 5-port gigabit
PHY. Logically:

```
  CPU  <--EDMA(0xc080000)-->  switch port 0 (CPU)
                              switch ports 1..4 (LAN)  --\
                              switch port 5     (WAN)  ---+-- QCA8075 PHYs (PSGMII)
                                                         (MDIO 0x90000, PSGMII cal 0x98000)
```

| Block | Base | Size | Source |
|-------|------|------|--------|
| EDMA registers | `0x0c080000` | `0x8000` | gale `board.c` (`soc/edma@c080000`), OpenWrt DT |
| ESS switch ("base") | `0x0c000000` | `0x80000` | OpenWrt `switch@c000000`, `reg-names="base"` |
| PSGMII PHY calibration | `0x00098000` | `0x800` | OpenWrt `reg-names="psgmii_phy"` |
| MDIO controller | `0x00090000` | `0x64` | OpenWrt `mdio@90000` |
| TCSR ESS config | `0x01953000` | — | U-Boot `RGMII_TCSR_ESS_CFG` |
| QFPROM (SoC unique id, MAC fallback) | `0x000a4000` region | — | gale `board.h` (`QFPROM_CORR_*`) |

> The EDMA base **0xc080000 is confirmed twice** (gale's DT fixup and the OpenWrt
> DT), so it is the most trustworthy address here.

## 2. PHY / port topology

QCA8075 exposes (over MDIO at `0x90000`):
- 5 per-port gigabit PHYs at MDIO addresses **0..4** (one per switch port 1..5)
- the internal **PSGMII PHY at MDIO address 5** (the calibration target;
  `priv->esw.phydev[num_phy-1]` in U-Boot)

Switch port roles (U-Boot `ess_switch_enable_lookup`):
- **port 0 = CPU** (faces EDMA; forced 1000M/full)
- **ports 1..4 = LAN**
- **port 5 = WAN**

**Open item:** which of the two physical RJ45 jacks on Google Wifi maps to which
switch port/PHY. Confirm from the coreboot gale DT or the OpenWrt
`ipq40xx/chromium` google_wifi target. For Phase 1 we only need *any one* port to
link, so this can be deferred — but record it before Phase 3.

## 3. Bring-up recipe (from U-Boot `essedma_probe` + `edma_init`)

Order matters. This is the sequence to reproduce:

1. **Clock + reset**: enable `GCC_ESS_CLK`, assert+deassert `ESS_RESET` (10 ms each).
   *Open item — may already be done by coreboot; see §7.*
2. **MDIO init**: clear `MDIO_MODE` bit 8 → clause-22 mode (`mdio_base + 0x40`).
3. **PSGMII analog cal (PSGMII mode)**: write to `psgmii_base`:
   - `PSGMIIPHY_PLL_VCO_RELATED_CTRL (0x78c) = PSGMIIPHY_PLL_VCO_VAL (0x2803)`
   - `PSGMIIPHY_VCO_CALIBRATION_CTRL_REGISTER_1 (0x9c) = PSGMIIPHY_VCO_VAL (0x4ada)`
   - wait 10 ms
   - `PSGMIIPHY_VCO_CALIBRATION_CTRL_REGISTER_1 (0x9c) = PSGMIIPHY_VCO_RST_VAL (0xada)`
4. **PSGMII self-test / calibration**: `psgmii_self_test()` — the loopback traffic
   calibration across all 5 PHYs, ≤20 retries. See §5. **(Riskiest step.)**
5. **Switch init**: `ess_switch_init()` — CPU port0 = 1000M/full/flow-control,
   per-port HOL queue config, enable port0 RX/TX MACs, forwarding magic values.
6. **EDMA init** (`edma_init`):
   - allocate TPD ring (TX, 8 desc) and RFD ring (RX, `PKTBUFSRX` desc), cache-line aligned
   - `ipq40xx_edma_stop_rx_tx()`
   - `ipq40xx_edma_configure()` — RSS off, RFD/TPD burst thresholds, RXQ/TXQ control
   - `ipq40xx_edma_init_desc()` — program ring base addrs, sizes, prod/cons idx
   - `ess_switch_disable_lookup()` (lookup enabled later, on link)
7. **On link up (`start`)**: `ipq40xx_edma_init_rfd_ring()` (fill RX buffers),
   `ipq40xx_edma_start_rx_tx()`, `ess_switch_enable_lookup()`.

## 4. EDMA registers & descriptors (offsets from `0xc080000`)

| Reg | Offset | Purpose |
|-----|--------|---------|
| `EDMA_REG_TX_SRAM_PART` | `0x400` | load-ptr bit (`1<<16`) commits base addrs |
| `EDMA_REG_TXQ_CTRL` | `0x404` | TXQ enable (`0x20`), TPD burst en (`0x100`) |
| `EDMA_REG_TXF_WATER_MARK` | `0x408` | TX FIFO watermarks (set 0) |
| `EDMA_REG_TPD_RING_SIZE` | `0x41C` | TPD ring size (mask `0xFFFF`) |
| `EDMA_REG_TPD_BASE_ADDR_Q(x)` | `0x420+4x` | TPD ring base (phys) |
| `EDMA_REG_TPD_IDX_Q(x)` | `0x460+4x` | prod idx (`[15:0]`), cons idx (`[31:16]`) |
| `EDMA_REG_RX_SW_CONS_IDX_Q(x)` | `0x220+4x` | SW RX consumer index |
| `EDMA_REG_TX_SW_CONS_IDX_Q(x)` | `0x240+4x` | SW TX consumer index |
| `EDMA_REG_RSS_TYPE` | `0x894` | RSS type (`0x1` = none) |
| `EDMA_REG_RFD_BASE_ADDR_Q(x)` | `0x950+4x` | RFD ring base (phys) |
| `EDMA_REG_RFD_IDX_Q(x)` | `0x9B0+4x` | RFD prod idx; cons idx (`[27:16]`) |
| `EDMA_REG_RX_DESC0` | `0xA10` | RFD ring size + RX buf size |
| `EDMA_REG_RX_DESC1` | `0xA14` | RFD burst / prefetch / low thresh |
| `EDMA_REG_RXQ_CTRL` | `0xA18` | RXQ enable (`0xFF00`), rmv-vlan (`0x2`) |
| `REG_MAC_CTRL0/1` | `0xC20/0xC24` | MAC address low/high |

Descriptors (`essedma.h`):
- **TPD** (TX, 16 bytes): `len`, `svlan_tag`, `word1` (EOP = `1<<31`), `addr` (phys),
  `word3` (port bitmap `EDMA_PORT_ENABLE_ALL=0x3E << 18`).
- **RRD** (RX return, 16 bytes): `rrd0..rrd7`; `rrd7 & 0x8000` = descriptor valid;
  `rrd6` = packet length. The RRD is prepended to the RX buffer.
- **RFD** (RX free): just a `buffer_addr` (phys).

### The 4-TPDs-per-packet trick
U-Boot sends each packet using **4 TPDs** (`EDMA_TPDS_PER_PACKET`) even though one
suffices, because the ARM cache line is larger than one 16-byte TPD and you cannot
flush a single TPD in isolation. depthcharge has the same constraint — keep this
trick (or align/pad rings so per-descriptor flush is safe).

## 5. PSGMII calibration / self-test (the risk)

The PSGMII SerDes between EDMA and the QCA8075 must be calibrated or links are
unreliable/absent. U-Boot's `psgmii_self_test()` (chosen to port **faithfully**):

- `psgmii_st_phy_prepare()` each port PHY (select copper page, power down, set
  packet count `0x8021`=4096 / size `0x8062`=1504 via MMD-AN, fix MDI).
- up to `PSGMII_ST_NUM_RETRIES` (20):
  - `qca8075_ess_reset()` — RX-20bit fix, PSGMII reset dance via BMCR
    `0x005b/0x001b/0x005b`, poll PLL_VCO_CALIB ready (PHY MMD PMAPMD `0x28` bit0,
    and `psgmii_base + 0xa0` bit0), freeze/release RX CDR (reg `0x1a` = `0x2230`/`0x3230`).
  - enable switch-port loopback on ports 1..5 (`ESS_PORT_LOOKUP_CTRL`, bit 21).
  - **serial test**: per PHY → reset+loopback (BMCR `0x9000` then `0x4140`), wait
    link (PHY specific reg `0x11` bit10), start traffic (MMD-AN `0x8020`=`0xa000`),
    wait egress counter (MMD-AN `0x802e`) == 4096, power down.
  - **parallel test**: same but all PHYs at once.
- recover each PHY (`psgmii_st_phy_recover`, disable loopback BMCR `0x9040`),
  disable switch loopback.

This needs **MMD (clause-45-indirect) MDIO helpers** on top of the clause-22 MDIO:
`phy_read_mmd`/`phy_write_mmd` use MII regs `0x0d` (MMD ctrl) and `0x0e` (MMD data).
QCA807x register names are in `essedma.h` (`QCA807X_*`, `PSGMIIPHY_*`).

## 6. MDIO controller (offsets from `0x90000`)

From `reference/uboot-mdio-ipq4019.c`:
- `MDIO_MODE_REG 0x40` (bit8: 0=clause22, 1=clause45)
- `MDIO_ADDR_REG 0x44` — `(phy_addr<<8)|reg`
- `MDIO_DATA_WRITE_REG 0x48`, `MDIO_DATA_READ_REG 0x4c`
- `MDIO_CMD_REG 0x50` — `BUSY=1<<16`, `START=1<<8`, code `0`=read/`1`=write
- Poll BUSY clear (timeout ~10000 × 10 µs). Trivial to port verbatim.

## 7. Open hardware questions (resolve during Phase 0/1)

1. **Clock/reset ownership**: does coreboot `firmware-gale-8281.B` already enable
   `GCC_ESS_CLK` and deassert `ESS_RESET`? If yes, the driver skips §3.1; if no,
   it must poke GCC directly (find the GCC base + ESS clk/reset bits). Determine by
   reading the EDMA ID/version reg early and seeing if it responds.
2. **Exact RJ45 ↔ switch-port/PHY map** for gale (see §2).
3. **PSGMII vs RGMII**: gale uses the internal QCA8075 → **PSGMII** path (assume
   `PHY_INTERFACE_MODE_PSGMII`). Confirm no board RGMII quirk.
4. **MAC address source**: reuse ipq806x.c's `lib_sysinfo.macs[0]` + QFPROM-SHA1
   fallback (already proven on this SoC family).

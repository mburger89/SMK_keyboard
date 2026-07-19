# Gateron LP 5×12 Wireless Keyboard — RP2040 + RM2 radio module, Rev B

59-key (5×12, bottom row 5 + 2U + 5) hot-swap low-profile keyboard. Chip-down
RP2040 + **Raspberry Pi Radio Module 2 (RM2, RMC20452T)** for Wi-Fi 4 /
Bluetooth 5.2, per-key SK6812MINI-E RGB, Li-ion + USB-C charging, hard power
switch.

Open `smk_kbd_rp2040.kicad_pro` (file saved by KiCad 10).

## Why RM2 (Rev B change)

Rev A used a bare CYW43439 WLBGA (0.4 mm pitch) which **requires HDI
fab** (laser microvias) — several $100s for a board this size. The RM2 module
($4, FCC/CE modular certified, antenna + crystal + RF matching included) puts
the BGA on Raspberry Pi's board instead, so this board is now a **standard
4-layer** — no microvias anywhere, cheapest 4-layer tier.

## RM2 integration (exact Pico W defaults — zero firmware config)

| Signal | RP2040 GPIO | RM2 pin |
|---|---|---|
| WL_ON (Wi-Fi on + BT on) | GPIO23 | 12 + 13 |
| gSPI DATA (in / out via R14 470 Ω / nIRQ via R15 10 kΩ) | GPIO24 | 5 / 6 / 10 |
| gSPI CS | GPIO25 | 9 |
| gSPI CLK | GPIO29 | 3 |
| Vin + VDDIO | — | 16 + 14 ← +3V3 |

Matches `CYW43_DEFAULT_PIN_*` in pico-sdk: build with `PICO_CYW43_SUPPORTED=1`
and cyw43-driver + BTstack work as on a Pico W. GPIO18-22, 28 are now spare.
RM2 GPIO0/1/2 (pins 8/18/17) left unconnected.

Module placed at the top-left board edge, antenna outward, with the
datasheet-mandated **RF keepout (rule area, all 4 copper layers, no
tracks/vias/pour)** covering the on-board part of the 35.5 × 18.5 mm zone.

## PCBWay order — STANDARD 4-layer

| Setting | Value |
|---|---|
| Board size | 234.5 × 116.5 mm |
| Layers | 4, standard stackup (dielectric 1 ≈ 0.21 mm kept) |
| Thickness | 1.6 mm |
| Min track/space | 0.105 mm used locally (3.5/3.5 mil capability), mostly ≥ 0.127 |
| Vias | through 0.6/0.3 only — **no microvias, no HDI** |
| Surface finish | ENIG or HASL (no BGA anymore; ENIG still nicer for the QFN/USON) |

1. Gerbers: `export_fab.py` with KiCad's bundled Python (fills zones, plots,
   drills, zips).
2. Assembly: `pcbway_production/2026-07-17_rm2_std4layer/bom_pcbway.csv` +
   `cpl_pcbway.csv` (SMT only; SW60/61 THT hand-solder; C18 gone — no RF
   tuning needed anymore, the RM2 is pre-tuned/certified).
3. RM2 sourcing: RMC20452T, $4 RRP, reel 960 — available from RPi distributors
   (SparkFun, Pimoroni, Farnell…). Likely consignment for PCBWay.

## History of fixes (Rev A → Rev B)

- QSPI_SD1/SD2 swap at the RP2040 (would not boot) — fixed in symbol, labels,
  nets, routing.
- USB_DM was unrouted — routed.
- Y1 (12 MHz) verified vs Pico: ABM8-272-T3 with 18p (fine).
- BAT+/EN_LDO/VSYS verified connected; RGB power budget note still applies
  (firmware must cap brightness).
- Discrete CYW43439 radio section fully removed (22 parts) along with its
  routing and all 41 laser microvias; QSPI/USB_DM re-routed through-via only.
- All connectivity + clearance verified by script after every step: every net
  one island; new copper ≥ 0.105 mm to foreign nets (PCBWay 4-layer min
  0.089); holes ≥ 0.25 mm; RF keepout free of all copper.

## Remaining before ordering

- Open in KiCad, fill zones (`B`), run DRC (project rules already set:
  clearance 0.09, annular 0.05). Expect only GND-unconnected warnings that
  the pour resolves, plus courtyard/silk cosmetics.
- Confirm RM2 stock and decide consign vs. PCBWay-sourced.
- The RM2 reflows like any SMT part (peak 260 °C); PCBWay should paste the 21
  castellation lands (paste layer is defined on the footprint).

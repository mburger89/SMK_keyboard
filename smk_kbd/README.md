# Gateron LP 5×12 Wireless Keyboard — KiCad Project

59-key (5×12, bottom row 5 + 2U + 5) hot-swap low-profile keyboard, ESP32-C6 wireless, Li-ion powered with USB-C charging and a hard power switch.

Open `smk_kbd.kicad_pro` in KiCad 9. Files are in KiCad 8 format, which KiCad 9 opens natively (it will save them forward in v9 format). All symbols and footprints are embedded **and** provided as project-local libraries (`kbd.pretty`, `kbd.kicad_sym`) so nothing external is required.

## Layout

- 19.05 mm pitch, rows 0–3 are full 12-key rows.
- Row 4: 5 keys (cols 0–4) + one **2U key** centered over the two middle 1U positions (electrically column 5) + 5 keys (cols 7–11). Column 6 has no switch in row 4.
- The 2U key uses the Gateron **plate-mounted** 2U stabilizer (KS-57B210T) — it clips to the plate, so the PCB needs no stabilizer holes. Keep the area around the 2U key clear of tall components (it already is).
- Board outline 234.5 × 116.5 mm; 6 × M2 mounting holes placed in the gaps between keys.

## Switch / socket footprint

Built from the Gateron datasheets you provided:

- ø5.2 mm center hole (stem post), 2 × ø3.0 mm contact barrels at (−4.4, 4.7) and (+2.6, 5.75) from switch center, 2.55 mm square solder pads on the **back** copper — sockets mount on the back, switches insert from the front.
- Verified against the KS-2P02B01-02 drawing (7.0 mm pin spread, 1.05 mm vertical offset, 14×14 body).

## Electrical design

**Matrix** — COL2ROW: `COL → switch → diode anode → cathode → ROW`. One 1N4148W (SOD-123, back side) per key, placed left of each switch.

**GPIO map (ESP32-C6-MINI-1)**

| Function | GPIO | Module pin |
|---|---|---|
| ROW0–ROW3 (inputs) | IO0–IO3 | 12, 13, 5, 6 |
| ROW4 (input) | IO5 | 10 |
| COL0–COL11 (outputs) | IO6, IO7, IO8, IO14, IO15, IO18–IO23, IO17 | 15, 16, 22, 19, 20, 24–29, 30 |
| VBAT sense (÷2) | IO4 / ADC1_CH4 | 9 |
| USB D− / D+ | IO12 / IO13 | 17 / 18 |
| BOOT button | IO9 | 23 |
| RESET button | EN | 8 |
| Spare / UART log | TXD0 (IO16) | 31 (unconnected) |

Rows are on IO0–IO3 + IO5 deliberately: these are **LP (low-power) GPIOs**, so the firmware can use them for deep-sleep key-press wakeup, and all are ADC-capable. Note IO4/IO5/IO8/IO9/IO15 are strapping pins — harmless for a matrix (inputs at boot), just don't hold keys during reset if flashing misbehaves.

**Power**

- USB-C (HRO TYPE-C-31-M-12, 16-pin USB 2.0) with 5.1 kΩ CC pulldowns → works with C-to-C cables. ESD protection via USBLC6-2SC6.
- Charger: MCP73831-2 with 2.0 kΩ PROG = **500 mA** charge current. Use a 1000 mAh+ Li-ion cell, or raise R3 to 10 kΩ for 100 mA with smaller cells. Charge LED on STAT.
- Power path (Feather-style): VBUS → Schottky (B5819W) → VSYS; battery → DMG3415U P-FET → VSYS. When USB is plugged in, the FET gate is pulled high and the board runs from USB while the battery charges; otherwise the FET conducts from the battery.
- **Charging works with the power switch OFF** — the charger connects to the battery ahead of the switch.
- ON/OFF: the side-actuated slide switch (MSK-12C02) sits flush with the rear board edge — its lever pokes out through a case cutout next to USB. It drives the AP2112K-3.3 LDO **EN** pin between VSYS and GND — it switches microamps, not the load current, and gives a true off state (LDO Iq ≈ 55 µA off the battery when on; ~0 when off).
- Battery voltage divider 1 MΩ/1 MΩ + 100 nF into IO4 for fuel-gauge readings.
- Battery connector: JST-SH 2-pin (SM02B-SRSS-TB), surface-mount on the **back** of the board, only ~1.6 mm tall, cable exits toward the board interior. Batteries usually ship with JST-PH plugs — order one with an SH plug or re-terminate. **Check polarity against the + mark before plugging in.**

## Routing — DONE

The board is **fully routed**: matrix (columns on F.Cu, rows on B.Cu, one via
per key), MCU fanout, USB differential pair, charger, power path, LDO and
buttons — 570 track segments, 130 vias, 29 GND stitching vias. An independent
geometric check verified 0.2 mm copper clearance, 0.3 mm hole clearance,
0.3 mm edge clearance and single-component connectivity for every net.
`board_render.png` shows the routed board (red = front, blue = back).

GND is carried by the two full-board pours — fill them before export (the
export script does this automatically).

## Sending to PCBWay

1. `cd` into this folder and run the export script with KiCad's bundled Python
   (it fills the zones, saves, and writes `smk_kbd_gerbers.zip`):

   macOS: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 export_fab.py`

   (Alternative: open the PCB in KiCad, press `B`, run DRC, then
   File → Fabrication Outputs → Gerbers + Drill Files and zip the output.)

2. Upload `smk_kbd_gerbers.zip` at pcbway.com → *Quick Order PCB*.

3. Order parameters:

   | Setting | Value |
   |---|---|
   | Board size | 234.5 × 116.5 mm |
   | Layers | 2 |
   | Thickness | **1.6 mm** |
   | Min track/spacing | 6/6 mil (design uses ≥ 0.2 mm — relaxed) |
   | Min hole | 0.3 mm |
   | Surface finish | HASL lead-free (or ENIG for nicer hot-swap pads) |
   | Copper | 1 oz |
   | Solder mask / silk | your choice |
   | Panelization | single piece |

4. Sanity checks before paying: view the Gerbers in PCBWay's online viewer or
   `gerbview` — confirm the GND pours are present on both layers (if they're
   missing you exported without filling zones) and the board outline is closed.

## PCB placement (why it routes easily)

- Socket pads are on the back; the **front layer is completely free under the matrix** — run columns vertically on F.Cu (each socket's COL pad is at the same x in a column; drop one via per key).
- Diodes are on the back, cathodes facing up — run rows horizontally on B.Cu. Row 4's 2U key is pre-assigned to column 5, so its column trace just jogs half a pitch.
- The diode anode pad sits 0.3 mm from its socket pad on the same net — join them with a stub trace.
- MCU/power strip along the top edge: battery + power mux + LDO left of the module, USB + ESD + charger right of it, BOOT/RESET buttons on the BACK of the board beside the module (press through case holes). Antenna points off the top edge with a built-in copper keepout zone (both layers) — don't route under it and keep the case plastic there.
- GND zones are defined on both layers — press `B` in pcbnew to fill.

## BOM (besides 59 switches, 59 sockets, keycaps, 2U plate stab)

| Ref | Part | Package |
|---|---|---|
| U1 | ESP32-C6-MINI-1 | SMD module |
| U2 | MCP73831-2ACI/OT | SOT-23-5 |
| U3 | AP2112K-3.3TRG1 | SOT-23-5 |
| U4 | USBLC6-2SC6 | SOT-23-6 |
| Q1 | DMG3415U (P-MOSFET) | SOT-23 |
| D1–D59 | 1N4148W | SOD-123 |
| D60 | B5819W / SS14 Schottky | SOD-123 |
| LED1 | LED (charge) | 0603 |
| J1 | HRO TYPE-C-31-M-12 (LCSC C165948) | SMD |
| J2 | JST SH **SM02B-SRSS-TB** (1.0 mm, low-profile side entry, on the **back**) | SMD |
| SW60/61 | 6×6 mm tactile (mounted on the **back** side) | THT |
| SW62 | MSK-12C02 side-actuated slide SPDT, lever exits rear edge | SMD |
| R1,R2 | 5.1 kΩ | 0603 |
| R3 | 2.0 kΩ | 0603 |
| R4 | 1 kΩ | 0603 |
| R5 | 100 kΩ | 0603 |
| R6,R7 | 1 MΩ | 0603 |
| R8 | 10 kΩ | 0603 |
| C1,C2 | 4.7 µF | 0603 |
| C3,C6 | 1 µF | 0603 |
| C4,C7 | 10 µF | 0603 |
| C5,C8 | 100 nF | 0603 |

## 3D models

Every footprint carries a 3D model, so KiCad's 3D viewer (`Alt+3`) shows the
assembled board:

- Switches: your `Gateron_KS-33.step` (in `3dmodels/`), one per key, plus a
  generated hot-swap socket model on the back side.
- ESP32-C6-MINI-1 and the MSK-12C02 slide switch: generated models in
  `3dmodels/` (dimensionally correct simplified shapes).
- Everything else (SOT-23s, 0603 R/C/LED, SOD-123 diodes, HRO USB-C, JST-PH,
  6 mm buttons) references KiCad 9's stock library via `${KICAD9_3DMODEL_DIR}`.
  If a part renders blank, install the "3D models" package from the KiCad
  installer — the references resolve automatically.

If the switch model appears rotated (LED window on the wrong side), edit one
footprint's model rotation and use Edit → "Change Footprints" to apply to all.

## Firmware notes

ZMK (with the ESP32 port) or ESP-IDF/Arduino work; the C6 supports BLE 5 + 802.15.4. Matrix: COL2ROW, diode direction col→row. Native USB (IO12/13) gives flashing and serial with no UART bridge; hold BOOT while tapping RESET for download mode.

## Final checks before ordering

1. Run `export_fab.py` (fills zones + saves), or open the PCB, press `B`, save.
2. Run KiCad's own DRC once for confidence — the design was verified by an independent geometric checker, but a second opinion is free.
3. Verify the slide-switch footprint against the exact part you buy (MSK-12C02 clones vary slightly).
4. The HRO USB-C legs are officially specced for thinner boards — they solder fine on 1.6 mm (standard practice on keyboards), or swap in a GCT USB4105 footprint if you prefer.

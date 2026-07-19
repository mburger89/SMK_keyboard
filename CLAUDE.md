# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A KiCad hardware project for a 59-key (5×12) hot-swap low-profile wireless
keyboard, in two MCU variants, **generated and routed entirely by Python
scripts** rather than hand-drawn in the KiCad GUI. The `.kicad_pcb` /
`.kicad_sch` files are build artifacts of these scripts, not the source of
truth — the source of truth is the Python that generates them.

- `smk_kbd/` — ESP32-C6-MINI-1 variant (BLE/802.15.4, module-based, no RGB).
- `smk_kbd_rp2040/` — RP2040 chip-down variant: RP2040 QFN-56 + external
  W25Q16JV QSPI flash + 12 MHz crystal + Infineon CYW43439 (BLE-only, WLAN held
  in reset) + 59× SK6812MINI-E per-key RGB over a single-wire chain through a
  SN74AHCT1G125 level shifter.

Both variants share the same mechanical layout, matrix topology, and
power/charging/USB circuitry; only the MCU/wireless/RGB sections differ.

## Build pipeline (root-level scripts, driven by plain `python3`)

For a given variant (`kbd` = ESP32 scripts, `_rp2040` = RP2040 scripts), the
pipeline is:

1. `generate_kbd.py` / `generate_kbd_rp2040.py` — emits the full KiCad project
   (schematic + PCB, footprints, symbols) from scratch into
   `smk_kbd/` / `smk_kbd_rp2040/`. Stdlib only (`uuid`, `os`,
   `json`) — no venv needed.
2. `add_3d.py` — attaches 3D models (generated VRML + stock KiCad models) to
   footprints, both in the board file and in `kbd.pretty`.
3. `route_kbd.py` / `route_kbd_rp2040.py` — parses the generated `.kicad_pcb`,
   pre-routes the key matrix deterministically (columns F.Cu, rows B.Cu, one
   via per key), then A*-routes everything else (MCU fanout, USB diff pair,
   charger, power path, LDO, buttons, RGB chain) on a 0.2 mm grid with exact
   clearance modeling, heals any split nets, adds GND stitching vias, and
   emits `tracks.sexp` / `tracks_rp2040.sexp` back into the board.
   **Requires the venv** (`numpy`, `sexpdata`; `route_kbd_rp2040.py` also pulls
   in `shapely` for A*): `.routing_venv/bin/python3 route_kbd.py` (or
   `route_kbd_rp2040.py`).
4. `drc_check.py` — independent geometric verification of the routed board:
   copper-copper clearance (≥0.19 mm), hole-copper clearance (≥0.25 mm),
   board-edge clearance (≥0.3 mm), and per-net connectivity (one connected
   component per net; GND islands are OK since the pour joins them). Run with
   the same venv: `.routing_venv/bin/python3 drc_check.py`. Exits 1 if any
   problem is found. Currently hardcoded to check `smk_kbd/smk_kbd.kicad_pcb`
   — edit the `PCB` constant at the top to point at the RP2040 board instead.
5. `export_fab.py` (inside each project folder) — must run under **KiCad's
   own bundled Python** (needs `pcbnew`), not the venv:
   `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 export_fab.py`.
   Fills GND zones, saves the board, and writes Gerbers + drill files to
   `fab/` plus a `*_gerbers.zip` for upload to PCBWay.

Regenerating a board means re-running steps 1–4 from the project root (the
scripts recreate the project directory contents); routing is deterministic
given the same generator output.

### Known gotcha: RP2040 `export_fab.py` targets the wrong board

`smk_kbd_rp2040/` contains a stray leftover copy of
`smk_kbd.kicad_pcb/.kicad_pro/.kicad_sch` (the ESP32 board's files),
and `smk_kbd_rp2040/export_fab.py` hardcodes `BOARD =
"smk_kbd.kicad_pcb"` — i.e. as-is it fills zones and exports the wrong
(ESP32) board file when run from that directory. Before exporting the RP2040
board for fab, fix `BOARD`/output names in that script to point at
`smk_kbd_rp2040.kicad_pcb`, or delete the stray ESP32 copy from that
folder.

## Electrical architecture

**Matrix (both variants):** COL2ROW — `COL → switch → diode anode → cathode →
ROW`, one 1N4148W per key. Row 4 is 5+2U(col 5)+5; columns 0–11, rows 0–4.

**Power/charging (identical on both boards, same component placement):**
USB-C (HRO TYPE-C-31-M-12) → USBLC6-2SC6 ESD → MCP73831-2 Li-ion charger
(500 mA via 2.0 kΩ PROG) → Feather-style power mux (Schottky from VBUS,
DMG3415U P-FET from battery) → VSYS → AP2112K-3.3 LDO, EN gated by a
side-actuated slide switch (true off state). Battery sense via a 1 MΩ/1 MΩ
divider into an ADC-capable GPIO.

**ESP32-C6 variant GPIO map and full BOM:** see `smk_kbd/README.md`.

**RP2040 variant:** ⚠️ `smk_kbd_rp2040/README.md` is a stale copy of
the ESP32 README (byte-identical) — do not trust it for RP2040-specific
pinout/BOM details. The authoritative source for that variant's design intent
and verification status is the module docstring at the top of
`generate_kbd_rp2040.py`, which tracks per-section confidence (matrix/power/
USB/charger/LDO unchanged from the verified ESP32 board; RP2040 pinout and
CYW43439 wiring individually re-verified against real datasheets, with
specific bugs found and fixed along the way — see recent commit history).

Known open items on the RP2040 variant (check `generate_kbd_rp2040.py`'s
docstring for the current state before relying on these):
- CYW43439 is a WLBGA-63 package at 0.4 mm ball pitch — no standard via fits
  between adjacent balls, so `route_kbd_rp2040.py` routes every net up to the
  footprint edge and stops; the final hop into the chip needs via-in-pad/
  microvia fab or manual routing.
- The antenna network's final matching capacitor (C17) is flagged as needing
  empirical tuning on the actual board/antenna, not a fixed catalog value.
- A few internal-rail decoupling cap values are marked VERIFY (no explicit
  datasheet number found for that specific ball).

## Verification methodology

This project treats "generated from a datasheet-shaped assumption" and
"verified against the actual datasheet PDF" as distinct confidence levels, and
the commit history is largely a sequence of upgrading specific claims (part
numbers, pinouts, package dimensions, power budgets, footprint geometry) from
the former to the latter — see recent `git log` messages and the datasheets
in `datasheets/`. When adding or modifying a component, prefer checking the
actual datasheet PDF over assuming a generic/typical value, and note the
verification status the way existing commits and docstrings do.

## Other repo contents

- `datasheets/` — reference PDFs for parts used in both designs (RP2040,
  CYW43439, SK6812MINI-E, W25Q16JV, level shifter, etc.) — check here before
  fetching a datasheet externally.
- `.routing_venv/` — local venv for the router's dependencies (`sexpdata`,
  `numpy`, `shapely`); gitignored.
- `*/analysis/` — output of the kicad-happy KiCad analyzer skill; regenerable,
  gitignored.
- `*/pcbway_production/` — timestamped fab-export snapshots (Gerbers, BOM,
  positions, IPC netlist) from prior export runs.
- `*/3dmodels/`, `*/shapes3D/` — generated/attached 3D models referenced by
  footprints.

## Available KiCad tooling

This session has access to `kicad-happy` skills (schematic/PCB analysis, EMC
pre-compliance checks, SPICE simulation of subcircuits, datasheet extraction,
BOM/distributor sourcing across DigiKey/Mouser/LCSC/element14, and JLCPCB/
PCBWay fab workflows) — reach for these instead of re-deriving analysis by
hand when reviewing or extending either board.

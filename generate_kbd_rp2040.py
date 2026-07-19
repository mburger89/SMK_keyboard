#!/usr/bin/env python3
"""Generate a complete KiCad project (schematic + PCB) for a 59-key
5x12 (bottom row 5+1+5, 2U center) wireless keyboard -- RP2040 variant.

MCU:      RP2040 chip-down (QFN-56) + external QSPI flash + 12MHz crystal
Wireless: Infineon CYW43439 chip-down (BLE), modeled on Raspberry Pi's
          Pico W reference design
RGB:      59x SK6812MINI-E per-key addressable LEDs, single-wire chain
Switches: Gateron KS-33 low profile 2.0
Sockets:  Gateron KS-2P02B01-02 hot-swap (footprint per Gateron datasheet)
Power:    Li-ion + MCP73831 charger + AP2112K-3.3 LDO + power mux + slide switch
USB:      HRO TYPE-C-31-M-12 (16P USB 2.0 Type-C, official KiCad pad map)

*** VERIFICATION STATUS (read before fab) ***
This variant was built without live datasheet access (research agents hit
the account's usage cap mid-session). Confidence by section:
  - Matrix, power tree, USB, charger, LDO: UNCHANGED from the verified
    ESP32 board -- same confidence as before.
  - RP2040 (pinout, package rotation, core supply): HIGH confidence -- pin
    numbers, dedicated-pin names, and the QFN-56 side rotation (which
    physical side pins 1-14/15-28/29-42/43-56 sit on) are transcribed from
    the real Raspberry Pi RP2040 Datasheet (Figure 3 "Pinout for QFN-56",
    Table 1 "Pin Descriptions", Table 2 "GPIO Bank 0 Functions"), not
    invented. This caught two real bugs in an earlier version of this file:
    (1) the core-supply section modeled the on-chip regulator as a buck
    converter needing an external inductor -- the real regulator (Section
    2.10, "Core Supply Regulator") is a simple linear/LDO type (VREG_VIN ->
    VREG_VOUT -> DVDD) needing only decoupling capacitors, no inductor;
    (2) the wireless UART was wired to GPIO18-21, but UART1's real
    alternate-function pins are GPIO20-23 (Table 2) -- BT_REG_ON/
    BT_DEV_WAKE (plain GPIOs) now sit on the freed-up GPIO18/19 instead.
    Also corrected: the real chip has no perimeter GND pins at all (GND is
    only the single exposed thermal pad) -- an earlier version invented
    several. QFN-56 pad pitch/size (0.4mm, 0.25x0.6mm) is still a generic
    IPC-nominal land pattern, not copied from Raspberry Pi's own drawing --
    verify that specifically before fab.
  - CYW43439 (wireless): MEDIUM-HIGH confidence -- rewritten against the real
    Infineon/Cypress CYW43439 datasheet (Document 002-30348 Rev *D): package
    is WLBGA-63 (0.4mm ball pitch, ~2.4x4.4mm body, fine-pitch -- needs
    professional stencil/reflow assembly, not hand-solderable), all 63 ball
    names/coordinates are transcribed from the datasheet's own ball table,
    crystal is the datasheet default 37.4MHz (not a guess), and Bluetooth is
    wired over its own dedicated 4-wire UART per datasheet sec. 9.2 -- NOT
    the WLAN SDIO/gSPI bus the original placeholder guessed. This variant is
    BLE-only, so WLAN is left permanently in reset (WL_REG_ON -> GND) and its
    SDIO/gSPI bus and GPIOs are unconnected. The RF antenna-matching network
    (L2/C17/C18) and crystal load caps (C30/C31) are now cross-checked
    against Raspberry Pi's own public Pico W hardware design files
    (RPi-PicoW-PUBLIC-20220607.zip, RPI-PICOW-R2.DSN -- same CYW43439 die,
    confirms 37.4MHz). C30/C31 (crystal load caps, 27pF) and R13 (crystal
    series resistor, 0R) are both confirmed against clean reference-
    designator-level evidence in that file (C257/C258 map 1:1 to the 27pF
    footprint -- exactly the pair a crystal load network needs -- and a 0R
    chip resistor sits on the same net as the wireless chip's crystal clock
    line; 27pF externals also work out to a physically sensible ~15.5-18.5pF
    effective load capacitance with typical PCB/pin stray, matching a
    standard-CL crystal). L2 (4.7nH match inductor) is likewise a confirmed
    real component family. Remaining VERIFY item: the antenna network's
    final capacitor value (C17, nominally 1pF here) -- even Raspberry Pi's
    own BOM shows this as an empirically-tuned per-board/per-antenna
    variant picked from a 0.2-2pF family, not one fixed number, so it still
    needs real tuning on THIS board's own antenna/trace; and a few
    internal-rail decoupling cap values marked VERIFY where neither source
    gave an explicit number for that specific ball.
  - QSPI flash (U5, W25Q16JVUXIQ): HIGH confidence -- this is the exact part
    Raspberry Pi's own Pico (RP2040's reference board) uses, confirmed
    against the official Winbond W25Q16JV datasheet (Rev G). Pin mapping
    (CS/DO-IO1/WP-IO2/GND/DI-IO0/CLK/HOLD-IO3/VCC) already matched the real
    pinout exactly. The footprint's body/pad dimensions were corrected to
    the datasheet's real USON-8 2x3x0.6mm land pattern (Section 11.4) --
    an earlier version used placeholder dimensions with the wrong aspect
    ratio. The "UXIQ" suffix decodes per the datasheet's ordering-code
    diagram: UX=8-pad USON 2x3mm package, I=industrial temp range,
    Q=green/RoHS package option -- a validly-constructed, real orderable
    part number, not just a plausible-looking guess.
  - RGB chain: HIGH confidence on the level shifter (U7) -- confirmed
    against TI's SN74AHCT1G125-Q1 datasheet (SCLS504E) that the part is
    real, comes in SOT-23-5 (TI's "DBV" package -- matches this file's
    footprint), has the exact OE/A/GND/Y/VCC pinout already modeled here,
    and specs a 3-5.5V operating range that covers this design's VSYS-fed
    VCC down to battery-empty voltages. Pinned to the specific TI part
    (SN74AHCT1G125DBVR) rather than the bare family name, since a same-
    numbered part from a different vendor (e.g. Nexperia's 74AHCT1G125)
    isn't a drop-in substitute here -- it doesn't come in SOT-23-5 at all,
    and specs a narrower 4.5-5.5V range that VSYS can drop below on
    battery. Power budget: HIGH confidence, now a calculated figure rather
    than "several amps" -- SK6812MINI-E's own datasheet (Dongguan Opsco,
    SPC/SK6812MINI-E Rev. 02) confirms 12mA/channel x 3 channels = 36mA/LED
    at full white, so 59 LEDs = 2.12A max. Two things this surfaced that
    weren't previously flagged: (1) D60 (B5819W Schottky, ~1A average
    current rating per its datasheet) sits in the VSYS path whenever
    USB-powered, and 2.12A would exceed it by >2x -- not just the
    already-documented AP2112K-3.3 LDO mismatch, which is correctly
    bypassed, but D60 is NOT bypassed; (2) the SK6812MINI-E's own VDD spec
    is 3.7-5.5V, and VSYS (fed from a single-cell Li-ion) can sag below
    3.7V within normal discharge range, not just as a battery-dead edge
    case -- the level shifter (verified separately, see above) only
    guarantees the DIN logic threshold is met, not that VDD itself stays
    in spec. Also added: a local 100nF decoupling cap per LED (C100-C158),
    matching the SK6812MINI-E datasheet's own typical application circuit
    ("even the capacitance between beads is essential") -- an earlier
    version of this file had only one bulk cap (C19) at the chain's start,
    59 LEDs away from the far end. Series resistor (R10, 330 ohm) and
    topology: MEDIUM-HIGH confidence, standard WS2812-family practice.
    LED (SK6812MINI-E, D1-D59): HIGH confidence -- confirmed against the
    real manufacturer datasheet (Dongguan Opsco Optoelectronics, Document
    SPC/SK6812MINI-E Rev. 02). Body is 3.2 x 2.8mm (an earlier version of
    this footprint modeled it as a 3.2x3.2 square) and, more importantly,
    pins 2 (DOUT) and 4 (DIN) were at swapped physical corners -- a bug
    invisible to the netlist (this script's own pin-to-net mapping was
    self-consistent either way) that would have put DOUT/DIN on the wrong
    physical pads with a real part soldered down. Both fixed.
    LED placement offset: was PITCH/2 (9.525mm) south of key center -- the
    midpoint of the gap to the NEXT row, nowhere near either switch's own
    south wall, so the LED illuminated nothing. Fixed to 5.9mm south, the
    standard south-facing SMD LED offset used across the open-source
    keyboard community for Cherry MX-compatible/low-profile switches
    (falls inside the switch's own 7.5mm courtyard, where south-facing
    switch housings have a light-pipe window -- confirmed clear of the
    switch's own SMD pads, which sit offset in X at this Y range).
  - Antenna (ANT1, keepout zone): a real, meaningful gap here, not just an
    unverified value -- an earlier version of this file had an antenna
    KEEPOUT ZONE but no actual antenna connected to it (WLRF_ANT_MID dead-
    ended at the DNP C18 with nothing beyond it), and that zone's own rules
    (pads/footprints not_allowed) would have made it impossible to ever
    place a real antenna there anyway. Fixed by adding a real, purchasable
    2.4GHz chip antenna (Johanson 2450AT18B100E, real datasheet, Ver. 4.0
    2018) inside the (now correctly-scoped) keepout zone, and switching
    L2/C17's matching values from the Pico W's own reference (which is
    tuned for a completely different, proprietary PCB-trace antenna, not
    this chip antenna) to Johanson's own published matching-network
    reference for this exact part. Remaining VERIFY: the feed trace from
    L2/C17/C18 to ANT1 isn't drawn yet (this variant ships unrouted by
    design), and the final matching values still need real RF tuning on
    this board's own layout -- true of any antenna matching network,
    confirmed by Johanson's own datasheet explicitly offering a free
    layout review before fab.
    ANTENNA FEED TRACE -- ROUTING REQUIREMENT (calculated, not a guess):
    this board is now a 4-layer stackup (F.Cu/prepreg/In1.Cu/core/In2.Cu/
    prepreg/B.Cu, 1.6mm overall -- see the `(setup (stackup ...))` block in
    build_pcb), converted from the original 2-layer board to resolve
    routing congestion elsewhere on the board (LED chain, QSPI escape).
    This changes the antenna feed trace's reference plane: the nearest
    continuous copper to F.Cu is no longer B.Cu 1.6mm away, it's In1.Cu
    only 0.2104mm away (the F.Cu-to-In1.Cu prepreg). Solving the standard
    Hammerstad-Jensen microstrip equations for 50 ohm against that much
    thinner dielectric (er~4.4) gives a required trace width of ~0.40mm --
    much narrower than the old 2-layer board's ~3.0mm figure, and closer
    to (but still distinct from) the ~0.25-0.3mm traces used for this
    board's ordinary digital signals. Whoever routes this board
    (route_kbd_rp2040.py or manual KiCad routing) must use a ~0.40mm-wide
    trace from U1's WLRF_2G_RF-fed net through L2/C17/C18 to ANT1's FEED
    pin, with a continuous, unbroken GND pour on In1.Cu directly beneath
    its entire length outside the antenna_keepout zone (inside that zone
    there's intentionally no ground reference, by design, right up to the
    antenna itself -- standard practice, not an oversight). Because In1.Cu
    is also being used for the matrix ROW trunks in the new stackup, this
    reference plane must be kept clear of trunk copper under the antenna
    feed specifically -- verify with the analyzer's zone/copper-presence
    check once routing is redone, not assumed. Secondary consideration
    for the same routing pass: U6's ball K1 (WLRF_2G_RF) sits on the SOUTH
    side of the chip (y=31.4) while ANT1 sits north of it (y=24.5) and L2
    sits further south still (y=34.5) -- the feed trace will have to jog
    around U6's own footprint rather than running in a straight line. At
    2.4GHz in this dielectric (er_eff~3.3), one wavelength is ~69mm, so a
    few mm of extra jog is a small fraction of a wavelength and not
    expected to be a functional blocker, but minimizing it is worth doing
    when real copper gets drawn.
Search this file for "VERIFY" to find every flagged item.

Files are written in KiCad 8 format, which KiCad 9 opens natively.
"""
import uuid, os, json

OUT = os.path.dirname(os.path.abspath(__file__))
PROJ = "smk_kbd_rp2040"
PRJDIR = os.path.join(OUT, PROJ)
os.makedirs(PRJDIR, exist_ok=True)

NS = uuid.UUID("12345678-1234-5678-1234-567812345678")
def U(*parts):
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts)))

_ctr = [0]
def NU(*parts):
    _ctr[0] += 1
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts) + f"#{_ctr[0]}"))

ROOT_UUID = U("root-sheet")

# ---------------------------------------------------------------- geometry
PITCH = 19.05
KX0, KY0 = 50.0, 50.0          # PCB center of key (row0,col0)
def key_xy(r, c):
    return (KX0 + c * PITCH, KY0 + r * PITCH)

# key list: (row, col, is2U)  -- row4: cols0-4, center 2U at c=5.5, cols7-11
KEYS = []
for r in range(4):
    for c in range(12):
        KEYS.append((r, c, False))
for c in range(5):
    KEYS.append((4, c, False))
KEYS.append((4, 5, True))       # 2U key, electrical column 5, x centered @5.5
for c in range(7, 12):
    KEYS.append((4, c, False))
assert len(KEYS) == 59

def key_pos(r, c, is2u):
    x, y = key_xy(r, c)
    if is2u:
        x = KX0 + 5.5 * PITCH
    return x, y

# ---------------------------------------------------------------- nets
NETS = ["", "GND", "+3V3", "VBUS", "VSYS", "BAT+", "EN_LDO", "VBAT_SENSE",
        "USB_DP", "USB_DM", "CC1", "CC2", "STAT", "PROG", "LED_A", "RUN", "BOOTSEL",
        # RP2040 minimum system -- power topology verified against the real
        # RP2040 datasheet's Core Supply Regulator chapter: the on-chip
        # regulator (VREG_VIN -> VREG_VOUT -> DVDD) is a simple linear/LDO
        # type needing only 1uF caps on VREG_VIN and VREG_VOUT plus 100nF on
        # each DVDD pin -- NO external inductor (an earlier version of this
        # file wrongly modeled it as a buck regulator with one).
        "VREG_VIN", "DVDD", "XIN", "XOUT",
        "QSPI_SCLK", "QSPI_SS", "QSPI_SD0", "QSPI_SD1", "QSPI_SD2", "QSPI_SD3",
        "SWCLK", "SWDIO",
        # CYW43439 wireless -- datasheet-verified net plan (Infineon/Cypress
        # CYW43439 datasheet 002-30348 Rev *D). BLE only: Bluetooth uses its
        # own dedicated 4-wire UART (sec. 9.2), NOT the WLAN SDIO/gSPI bus,
        # so WL_REG_ON is tied to GND to hold the WLAN section permanently
        # in reset and that whole bus is left unconnected (see CYW_BALLNET).
        "BT_UART_RXD", "BT_UART_TXD", "BT_UART_CTS_N", "BT_UART_RTS_N",
        "BT_DEV_WAKE", "BT_HOST_WAKE", "BT_REG_ON",
        "CYW_SR_VLX", "CYW_VDD1P5", "CYW_XTAL_VDD1P2", "CYW_VOUT_CLDO",
        "CYW_VOUT_LNLDO", "CYW_VOUT_3P3", "CYW_PA_VDD",
        "CYW_BT_VCO_VDD", "CYW_BTFM_PLL_VDD", "CYW_BT_IF_VDD",
        "WLRF_ANT", "WLRF_ANT_MID", "CYW_XTAL_XOP", "CYW_XTAL_XON", "CYW_XTAL_XON_J",
        # RGB chain
        "RGB_GPIO", "LEDD0_R"]
ROWN = {r: len(NETS) + r for r in range(5)}
NETS += [f"ROW{r}" for r in range(5)]
COLN = {c: len(NETS) + c for c in range(12)}
NETS += [f"COL{c}" for c in range(12)]
KEYNET = {}
for (r, c, u2) in KEYS:
    KEYNET[(r, c)] = len(NETS)
    NETS.append(f"N_R{r}C{c}")

# ---- RGB chain order: serpentine, must match Sources/smk/RGBLighting.swift's
# ledChainIndex() -- even rows col0->max, odd rows col(max)->0. Chain net i is
# "LEDD{i}": LEDD0 = level-shifter output -> LED #1 DIN; LEDD{i} = LED{i}.DOUT
# -> LED{i+1}.DIN; last entry is LED59's DOUT (chain end, no connect).
LED_CHAIN = []  # ordered list of (row, col) in physical chain order
for r in range(5):
    row_keys = sorted([(rr, cc) for (rr, cc, u2) in KEYS if rr == r],
                      key=lambda rc: rc[1], reverse=(r % 2 == 1))
    LED_CHAIN.extend(row_keys)
assert len(LED_CHAIN) == 59
LEDDN = {}
for i in range(len(LED_CHAIN) + 1):
    LEDDN[i] = len(NETS)
    NETS.append(f"LEDD{i}")
NETI = {n: i for i, n in enumerate(NETS)}

# ---- RP2040 pinout: single source of truth for BOTH the schematic symbol
# and the PCB footprint (fp_rp2040 pad numbers), so they can't drift apart.
# Pin numbers and dedicated-pin names below are transcribed from the real
# Raspberry Pi RP2040 Datasheet (datasheets.raspberrypi.com/rp2040/
# rp2040-datasheet.pdf), Figure 3 "RP2040 Pinout for QFN-56" and Table 1
# "Pin Descriptions" -- not invented. The only real chip fact that changed
# this design: real GND is ONLY the single exposed thermal pad (Table 1:
# "Single external ground connection, bonded to a number of internal
# ground pads") -- the chip has no perimeter GND pins, unlike an earlier
# version of this file which invented several. GPIO function ASSIGNMENTS
# (which GPIO does which job -- rows/cols/RGB/BT UART/etc.) are this
# project's own choice within that real physical pin map; UART1's real
# alternate-function pins are GPIO20-23 (datasheet Table 2), which is why
# BT_REG_ON/BT_DEV_WAKE (plain GPIOs, no alt-function needed) sit on the
# freed-up GPIO18/19 instead of GPIO20-23.
# Tuple: (pin_num, label, net_name)
RP2040_PINOUT = [
    (1, "IOVDD", "+3V3"),
    (2, "GPIO0", "ROW0"), (3, "GPIO1", "ROW1"), (4, "GPIO2", "ROW2"),
    (5, "GPIO3", "ROW3"), (6, "GPIO4", "ROW4"),
    (7, "GPIO5", "COL0"), (8, "GPIO6", "COL1"), (9, "GPIO7", "COL2"),
    (10, "IOVDD", "+3V3"),
    (11, "GPIO8", "COL3"), (12, "GPIO9", "COL4"), (13, "GPIO10", "COL5"),
    (14, "GPIO11", "COL6"), (15, "GPIO12", "COL7"), (16, "GPIO13", "COL8"),
    (17, "GPIO14", "COL9"), (18, "GPIO15", "COL10"),
    (19, "TESTEN", "GND"),      # datasheet: "Factory test mode pin. Tie to GND."
    (20, "XIN", "XIN"), (21, "XOUT", "XOUT"),
    (22, "IOVDD", "+3V3"),
    (23, "DVDD", "DVDD"),
    (24, "SWCLK", "SWCLK"), (25, "SWDIO", "SWDIO"),
    (26, "RUN", "RUN"),
    (27, "GPIO16", "COL11"), (28, "GPIO17", "RGB_GPIO"),
    # CYW43439 Bluetooth is a dedicated 4-wire UART (sec. 9.2 of its own
    # datasheet), not the WLAN SDIO/gSPI bus -- BLE-only variant.
    (29, "GPIO18", "BT_REG_ON"), (30, "GPIO19", "BT_DEV_WAKE"),
    (31, "GPIO20/UART1_TX", "BT_UART_RXD"), (32, "GPIO21/UART1_RX", "BT_UART_TXD"),
    (33, "IOVDD", "+3V3"),
    (34, "GPIO22/UART1_CTS", "BT_UART_RTS_N"), (35, "GPIO23/UART1_RTS", "BT_UART_CTS_N"),
    (36, "GPIO24", None), (37, "GPIO25", None),
    (38, "GPIO26/ADC0", "VBAT_SENSE"), (39, "GPIO27/ADC1", None),
    (40, "GPIO28/ADC2", "BT_HOST_WAKE"), (41, "GPIO29/ADC3", None),
    (42, "IOVDD", "+3V3"),
    (43, "ADC_AVDD", "+3V3"),
    (44, "VREG_VIN", "VREG_VIN"), (45, "VREG_VOUT", "DVDD"),
    (46, "USB_DM", "USB_DM"), (47, "USB_DP", "USB_DP"),
    (48, "USB_VDD", "+3V3"),
    (49, "IOVDD", "+3V3"),
    (50, "DVDD", "DVDD"),
    (51, "QSPI_SD3", "QSPI_SD3"), (52, "QSPI_SCLK", "QSPI_SCLK"),
    (53, "QSPI_SD0", "QSPI_SD0"), (54, "QSPI_SD2", "QSPI_SD2"),
    (55, "QSPI_SD1", "QSPI_SD1"), (56, "QSPI_SS_N", "QSPI_SS"),
]
RP2040_THERMAL_PAD = 57  # exposed pad -- the chip's only ground connection

def net(name):
    if name is None:
        return ""
    return f'(net {NETI[name]} "{name}")'

# ---------------------------------------------------------------- pcb pads
def pad(num, ptype, shape, x, y, sx, sy, layers, netname=None, rot=0.0,
        drill=None, extra=""):
    d = f"(drill {drill}) " if drill else ""
    n = net(netname) if netname else ""
    numtxt = f'"{num}"'
    at = f"(at {x:g} {y:g}{'' if rot==0 else f' {rot:g}'})"
    return (f'    (pad {numtxt} {ptype} {shape} {at} (size {sx:g} {sy:g}) {d}'
            f'(layers {layers}) {n}{extra} (uuid "{NU("pad",num,x,y)}"))')

def npth(x, y, dia):
    return (f'    (pad "" np_thru_hole circle (at {x:g} {y:g}) (size {dia:g} {dia:g}) '
            f'(drill {dia:g}) (layers "F&B.Cu" "*.Mask") (uuid "{NU("npth",x,y)}"))')

def fpline(x1, y1, x2, y2, layer, w=0.12):
    return (f'    (fp_line (start {x1:g} {y1:g}) (end {x2:g} {y2:g}) '
            f'(stroke (width {w}) (type solid)) (layer "{layer}") (uuid "{NU("l",layer,x1,y1,x2,y2)}"))')

def fprect(x1, y1, x2, y2, layer, w=0.1):
    return (f'    (fp_rect (start {x1:g} {y1:g}) (end {x2:g} {y2:g}) '
            f'(stroke (width {w}) (type solid)) (fill none) (layer "{layer}") (uuid "{NU("r",layer,x1,y1,x2,y2)}"))')

def fparc(sx, sy, mx, my, ex, ey, layer, w=0.12):
    return (f'    (fp_arc (start {sx:g} {sy:g}) (mid {mx:g} {my:g}) (end {ex:g} {ey:g}) '
            f'(stroke (width {w}) (type solid)) (layer "{layer}") (uuid "{NU("a",layer,sx,sy,ex,ey)}"))')

# ---------------------------------------------------------------- 3D models
# KiCad's own standard library, referenced by absolute path -- this machine's
# KiCad 10 install has no env var configured for it (checked
# ~/Library/Preferences/kicad/10.0/kicad_common.json, "vars": null), so a
# portable ${KICADxx_3DMODEL_DIR}-style reference isn't reliable here. If you
# move this project to another machine, re-point KICAD3D or add the env var
# in KiCad's own path configuration dialog.
KICAD3D = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels"
# This project's own hand-modeled/vendor-STEP parts, referenced relative to
# the project directory so they stay portable across machines.
PROJ3D = "${KIPRJMOD}/3dmodels"

def model(path, scale=(1, 1, 1), offset=(0, 0, 0), rotate=(0, 0, 0)):
    return (f'    (model "{path}"\n'
            f'      (offset (xyz {offset[0]:g} {offset[1]:g} {offset[2]:g}))\n'
            f'      (scale (xyz {scale[0]:g} {scale[1]:g} {scale[2]:g}))\n'
            f'      (rotate (xyz {rotate[0]:g} {rotate[1]:g} {rotate[2]:g}))\n'
            f'    )')

def fp_header(lib_fp, ref, val, x, y, rot, layer="F.Cu", attr="smd",
              ref_at=(0, -3.5), ref_layer=None, path_uuid=None, val_at=(0, 3.5)):
    rl = ref_layer or ("B.SilkS" if layer == "B.Cu" else "F.SilkS")
    fl = "B.Fab" if layer == "B.Cu" else "F.Fab"
    mirror = " (justify mirror)" if layer == "B.Cu" else ""
    p = f'  (path "/{path_uuid}")\n' if path_uuid else ""
    atrot = "" if rot == 0 else f" {rot:g}"
    return f'''  (footprint "{lib_fp}" (layer "{layer}")
  (uuid "{U("fp", ref)}")
  (at {x:g} {y:g}{atrot})
  (property "Reference" "{ref}" (at {ref_at[0]:g} {ref_at[1]:g} {(-rot)%360:g}) (layer "{rl}") (uuid "{U("fpref",ref)}")
    (effects (font (size 1 1) (thickness 0.15)){mirror})
  )
  (property "Value" "{val}" (at {val_at[0]:g} {val_at[1]:g} {(-rot)%360:g}) (layer "{fl}") (uuid "{U("fpval",ref)}")
    (effects (font (size 1 1) (thickness 0.15)){mirror})
  )
  (property "Footprint" "{lib_fp}" (at 0 0 0) (layer "{fl}") (hide yes) (uuid "{U("fpfp",ref)}")
    (effects (font (size 1.27 1.27))))
  (property "Datasheet" "" (at 0 0 0) (layer "{fl}") (hide yes) (uuid "{U("fpds",ref)}")
    (effects (font (size 1.27 1.27))))
  (property "Description" "" (at 0 0 0) (layer "{fl}") (hide yes) (uuid "{U("fpdesc",ref)}")
    (effects (font (size 1.27 1.27))))
{p}  (attr {attr})
'''

# ---- Gateron KS-33 hot-swap socket footprint (pads on back copper) --------
def fp_gateron(ref, x, y, n_pad1, n_pad2, path_uuid, is2u=False):
    # Value = the hot-swap SOCKET (the soldered part, and the BOM line);
    # the KS-33 switch plugs into it and is ordered separately. Matches
    # the schematic symbols' value so sch/PCB cross-checks stay clean.
    # No exclude_from_pos_files: the socket is a real reflowed SMD part
    # (the BOM line for each key position), so it must appear in the
    # placement files if an assembly service places it.
    #
    # Anchored on B.Cu so KiCad buckets it into the BOTTOM-side position
    # file -- that's where the socket is physically placed and reflowed
    # (its solder pads have always been on B.Cu; only the anchor layer
    # changes here). No stored coordinate changes: this generator
    # authors footprints in final stored coordinates, exactly as KiCad
    # itself stores back-side footprints (KiCad's flip bakes the mirror
    # into the file rather than reinterpreting at render time -- see
    # fp_sk6812mini's comment), so every pad/hole/graphic stays at the
    # same global position and all existing routing remains valid.
    # fp_header handles the B.Cu text conventions (ref -> B.SilkS,
    # value -> B.Fab, both justify-mirrored). Known cosmetic caveat:
    # the two attached 3D models (switch on front, socket behind) were
    # oriented for a front-anchored footprint; the 3D viewer applies
    # its back-side transform to models of B.Cu footprints, so the
    # preview may show them flipped -- fab outputs are unaffected.
    s = fp_header("kbd:SW_Gateron_KS33_HS", ref, "KS-2P02B01-02", x, y, 0,
                  layer="B.Cu", attr="smd",
                  ref_at=(0, -8.7), path_uuid=path_uuid, val_at=(0, 8.7))
    body = []
    # switch body / keycap guides
    body.append(fprect(-7.0, -7.0, 7.0, 7.0, "F.Fab"))
    body.append(fprect(-7.5, -7.5, 7.5, 7.5, "F.CrtYd", 0.05))
    body.append(fprect(-9.7, -7.5, 7.9, 7.5, "B.CrtYd", 0.05))
    if is2u:
        body.append(fprect(-19.05, -9.525, 19.05, 9.525, "Dwgs.User"))
    else:
        body.append(fprect(-9.525, -9.525, 9.525, 9.525, "Dwgs.User"))
    # socket outline on back silk (from datasheet drawing)
    for ln in [(-7,2.53,-3,2.53),(-1.5,3.58,-3,2.53),(-1.5,3.58,5.2,3.58),
               (5.2,3.58,5.2,4.08),(-7,2.53,-7,3.03),(-7,6.37,-7,6.87),
               (-7,6.87,-3.5,6.87),(-2,7.92,-3.5,6.87),(-2,7.92,5.2,7.92),
               (5.2,7.92,5.2,7.42)]:
        body.append(fpline(*ln, "B.SilkS", 0.15))
    # holes per Gateron KS-2P02B01-02 datasheet
    body.append(npth(0, 0, 5.2))          # center stem (5.1 dwg +0.1 clearance)
    body.append(npth(-4.4, 4.7, 3.0))     # socket contact barrels
    body.append(npth(2.6, 5.75, 3.0))
    body.append(pad(1, "smd", "rect", -8.275, 4.7, 2.55, 2.55,
                    '"B.Cu" "B.Paste" "B.Mask"', n_pad1))
    body.append(pad(2, "smd", "rect", 6.475, 5.75, 2.55, 2.55,
                    '"B.Cu" "B.Paste" "B.Mask"', n_pad2))
    # Two models: the hot-swap socket itself (soldered to B.Cu, sits behind
    # the board) and the switch that plugs into it (sits in front) -- both
    # centered on this footprint's own origin already (confirmed: the real
    # Gateron_KS-33.step bounding box is exactly -7.5..7.5mm in X/Y, matching
    # this footprint's own F.CrtYd). gateron_socket.wrl is a simple hand-
    # authored placeholder (no real vendor model for the KS-2P02B01-02
    # socket), scaled 2.54 per its own inch-like native units (verified
    # against usb_c_hro.wrl's body block, which matches this footprint's
    # real 8.94x7.30mm F.Fab size exactly at that scale).
    # Both models were authored for the old F.Cu-anchored footprint
    # (switch above the board, socket behind). With the anchor now on
    # B.Cu, the 3D viewer applies its back-side transform (180-degree
    # flip about the footprint origin plus re-basing to the bottom
    # surface) to every attached model -- which put the socket on top
    # and the switch underneath. The stored rotate/offset below is the
    # exact inverse of that transform, so both models render in their
    # original, physically-correct world positions. Axis determined
    # empirically with kicad-cli renders against the pre-flip board:
    # the viewer's back-side flip is 180 degrees about the footprint's
    # Y axis (an X-axis guess left every switch 180 degrees rotated
    # in-plane -- visible as the body's corner tabs swapping edges).
    flip_rot = (0, 180, 0)
    flip_off = (0, 0, -1.6)   # board thickness
    body.append(model(f"{PROJ3D}/Gateron_KS-33.step",
                      rotate=flip_rot, offset=flip_off))
    body.append(model(f"{PROJ3D}/gateron_socket.wrl", scale=(2.54, 2.54, 2.54),
                      rotate=flip_rot, offset=flip_off))
    return s + "\n".join(body) + "\n  )\n"

# ---- SOD-123 diode on the back --------------------------------------------
def fp_diode(ref, x, y, rot, n_k, n_a, path_uuid, val="1N4148W"):
    s = fp_header("kbd:D_SOD-123_Back", ref, val, x, y, rot,
                  layer="B.Cu", attr="smd", ref_at=(0, -2.2), val_at=(0, 2.2),
                  path_uuid=path_uuid)
    b = []
    b.append(pad(1, "smd", "rect", -1.635, 0, 1.0, 1.2,
                 '"B.Cu" "B.Paste" "B.Mask"', n_k, rot=rot))
    b.append(pad(2, "smd", "rect", 1.635, 0, 1.0, 1.2,
                 '"B.Cu" "B.Paste" "B.Mask"', n_a, rot=rot))
    b.append(fprect(-1.4, -0.9, 1.4, 0.9, "B.Fab"))
    b.append(fpline(-2.3, -1.0, -2.3, 1.0, "B.SilkS", 0.12))   # cathode bar
    b.append(fpline(-2.3, -1.0, 1.6, -1.0, "B.SilkS", 0.12))
    b.append(fpline(-2.3, 1.0, 1.6, 1.0, "B.SilkS", 0.12))
    b.append(fprect(-2.5, -1.15, 2.5, 1.15, "B.CrtYd", 0.05))
    b.append(model(f"{KICAD3D}/Diode_SMD.3dshapes/D_SOD-123.step"))
    # NB: (path) header line: fp_header already handled path via arg
    return s + "\n".join(b) + "\n  )\n"

# NOTE for diode: pad local coords are rotated by footprint rot via pad rot arg

# ---- ESP32-C6-MINI-1 (official Espressif geometry) ------------------------
ESP_PINNET = {}  # pad -> net name, filled in main
def fp_esp32(ref, x, y, path_uuid, pinnet):
    s = fp_header("kbd:ESP32-C6-MINI-1", ref, "ESP32-C6-MINI-1", x, y, 0,
                  ref_at=(0, -9.5), path_uuid=path_uuid, val_at=(0, 9.85))
    b = []
    def pnet(n):
        return pinnet.get(n)
    # left column pins 1-11
    ys = [-1.3 + 0.8 * i for i in range(11)]
    for i, py in enumerate(ys, start=1):
        b.append(pad(i, "smd", "rect", -5.9, py, 0.4, 0.8,
                     '"F.Cu" "F.Paste" "F.Mask"', pnet(i), rot=90))
    # bottom row pins 12-24
    for i in range(13):
        b.append(pad(12 + i, "smd", "rect", -4.8 + 0.8 * i, 7.6, 0.4, 0.8,
                     '"F.Cu" "F.Paste" "F.Mask"', pnet(12 + i)))
    # right column pins 25-35
    for i in range(11):
        b.append(pad(25 + i, "smd", "rect", 5.9, 6.7 - 0.8 * i, 0.4, 0.8,
                     '"F.Cu" "F.Paste" "F.Mask"', pnet(25 + i), rot=90))
    # top inner row pins 36-48
    for i in range(13):
        b.append(pad(36 + i, "smd", "rect", 4.8 - 0.8 * i, -2.2, 0.4, 0.8,
                     '"F.Cu" "F.Paste" "F.Mask"', pnet(36 + i)))
    # thermal pad 49 (3x3 grid of 1.45mm squares)
    for px in (-1.975, 0, 1.975):
        for py in (0.725, 2.7, 4.675):
            b.append(pad(49, "smd", "rect", px, py, 1.45, 1.45,
                         '"F.Cu" "F.Paste" "F.Mask"', pnet(49), rot=90,
                         extra=" (zone_connect 2)"))
    # corner pads 50-53
    for i, (px, py) in enumerate([(5.95, -2.25), (5.95, 7.65),
                                  (-5.95, 7.65), (-5.95, -2.25)], start=50):
        b.append(pad(i, "smd", "rect", px, py, 0.7, 0.7,
                     '"F.Cu" "F.Paste" "F.Mask"', pnet(i), rot=90))
    # outlines
    b.append(fprect(-6.6, -8.3, 6.6, 8.3, "F.Fab"))
    b.append(fpline(-6.6, -2.9, 6.6, -2.9, "F.Fab"))
    b.append(fprect(-6.8, -8.5, 6.8, 8.5, "F.CrtYd", 0.05))
    b.append(fpline(-6.6, -8.3, 6.6, -8.3, "F.SilkS"))
    b.append(fpline(-6.6, 8.3, 6.6, 8.3, "F.SilkS"))
    b.append(fpline(-6.6, -8.3, -6.6, 8.3, "F.SilkS"))
    b.append(fpline(6.6, -8.3, 6.6, 8.3, "F.SilkS"))
    b.append(fpline(-6.6, -2.9, 6.6, -2.9, "F.SilkS"))
    b.append(f'''    (fp_text user "ANTENNA - keep copper clear" (at 0 -5.6) (layer "F.SilkS") (uuid "{U('esptxt',ref)}")
      (effects (font (size 0.8 0.8) (thickness 0.12))))''')
    return s + "\n".join(b) + "\n  )\n"

# ---- USB-C HRO TYPE-C-31-M-12 (official KiCad pad map) ---------------------
def fp_usbc(ref, x, y, rot, path_uuid, padnet):
    s = fp_header("kbd:USB_C_Receptacle_HRO_TYPE-C-31-M-12", ref, "TYPE-C-31-M-12",
                  x, y, rot, ref_at=(0, -5.6), path_uuid=path_uuid, val_at=(0, 5.1))
    b = []
    sig = [("A1", -3.25, 0.6), ("B12", -3.25, 0.6), ("A4", -2.45, 0.6),
           ("B9", -2.45, 0.6), ("B8", -1.75, 0.3), ("A5", -1.25, 0.3),
           ("B7", -0.75, 0.3), ("A6", -0.25, 0.3), ("A7", 0.25, 0.3),
           ("B6", 0.75, 0.3), ("A8", 1.25, 0.3), ("B5", 1.75, 0.3),
           ("B4", 2.45, 0.6), ("A9", 2.45, 0.6), ("B1", 3.25, 0.6),
           ("A12", 3.25, 0.6)]
    for name, px, w in sig:
        b.append(pad(name, "smd", "rect", px, -4.045, w, 1.45,
                     '"F.Cu" "F.Paste" "F.Mask"', padnet.get(name), rot=rot))
    for px, py, h, dh in [(4.32, 1.05, 1.6, 1.2), (-4.32, 1.05, 1.6, 1.2),
                          (4.32, -3.13, 2.1, 1.7), (-4.32, -3.13, 2.1, 1.7)]:
        b.append(f'    (pad "S1" thru_hole oval (at {px:g} {py:g} {rot:g}) (size 1 {h:g}) '
                 f'(drill oval 0.6 {dh:g}) (layers "*.Cu" "*.Mask") {net(padnet.get("S1"))} '
                 f'(uuid "{NU("usbs1", px, py)}"))')
    b.append(npth(2.89, -2.6, 0.65))
    b.append(npth(-2.89, -2.6, 0.65))
    b.append(fprect(-4.47, -3.65, 4.47, 3.65, "F.Fab"))
    b.append(fprect(-5.32, -5.27, 5.32, 4.15, "F.CrtYd", 0.05))
    b.append(fpline(-4.7, 2.0, -4.7, 3.9, "F.SilkS"))
    b.append(fpline(4.7, 2.0, 4.7, 3.9, "F.SilkS"))
    b.append(fpline(-4.7, 3.9, 4.7, 3.9, "F.SilkS"))
    # usb_c_hro.wrl's main body block is 3.5197x2.8740 native units; at the
    # 2.54 scale below that's 8.94x7.30mm, matching this footprint's own
    # F.Fab rect (8.94x7.30mm) exactly -- confirms both the scale factor and
    # that the model is already centered on this footprint's origin.
    b.append(model(f"{PROJ3D}/usb_c_hro.wrl", scale=(2.54, 2.54, 2.54)))
    return s + "\n".join(b) + "\n  )\n"

# ---- small generic packages ------------------------------------------------
def fp_sot23_5(ref, val, x, y, rot, path_uuid, pinnet, npins=5):
    s = fp_header(f"kbd:SOT-23-{npins}", ref, val, x, y, rot,
                  ref_at=(0, -2.7), path_uuid=path_uuid, val_at=(0, 2.7))
    b = []
    bot = [(1, -0.95), (2, 0.0), (3, 0.95)]
    top = [(4, 0.95), (5, -0.95)] if npins == 5 else [(4, 0.95), (5, 0.0), (6, -0.95)]
    for n, px in bot:
        b.append(pad(n, "smd", "rect", px, 1.3, 0.6, 1.2,
                     '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(n), rot=rot))
    for n, px in top:
        b.append(pad(n, "smd", "rect", px, -1.3, 0.6, 1.2,
                     '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(n), rot=rot))
    b.append(fprect(-1.45, -0.85, 1.45, 0.85, "F.Fab"))
    b.append(fpline(-1.45, 1.0, -1.45, 0.85, "F.SilkS"))
    b.append(fpline(-1.7, 1.75, -1.45, 1.75, "F.SilkS"))  # pin1 mark
    b.append(fprect(-1.7, -2.0, 1.7, 2.0, "F.CrtYd", 0.05))
    b.append(model(f"{KICAD3D}/Package_TO_SOT_SMD.3dshapes/SOT-23-{npins}.step"))
    return s + "\n".join(b) + "\n  )\n"

def fp_sot23(ref, val, x, y, rot, path_uuid, pinnet):
    s = fp_header("kbd:SOT-23", ref, val, x, y, rot,
                  ref_at=(0, -2.7), path_uuid=path_uuid, val_at=(0, 2.7))
    b = []
    b.append(pad(1, "smd", "rect", -0.95, 1.1, 0.9, 1.0,
                 '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(1), rot=rot))
    b.append(pad(2, "smd", "rect", 0.95, 1.1, 0.9, 1.0,
                 '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(2), rot=rot))
    b.append(pad(3, "smd", "rect", 0.0, -1.1, 0.9, 1.0,
                 '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(3), rot=rot))
    b.append(fprect(-1.45, -0.65, 1.45, 0.65, "F.Fab"))
    b.append(fprect(-1.7, -1.8, 1.7, 1.8, "F.CrtYd", 0.05))
    b.append(model(f"{KICAD3D}/Package_TO_SOT_SMD.3dshapes/SOT-23.step"))
    return s + "\n".join(b) + "\n  )\n"

def fp_0603(ref, val, x, y, rot, path_uuid, n1, n2, led=False):
    s = fp_header("kbd:LED_0603" if led else "kbd:RC_0603", ref, val, x, y, rot,
                  ref_at=(0, -1.5), path_uuid=path_uuid, val_at=(0, 1.5))
    b = []
    b.append(pad(1, "smd", "roundrect", -0.775, 0, 0.9, 1.0,
                 '"F.Cu" "F.Paste" "F.Mask"', n1, rot=rot,
                 extra=" (roundrect_rratio 0.25)"))
    b.append(pad(2, "smd", "roundrect", 0.775, 0, 0.9, 1.0,
                 '"F.Cu" "F.Paste" "F.Mask"', n2, rot=rot,
                 extra=" (roundrect_rratio 0.25)"))
    b.append(fprect(-0.8, -0.4, 0.8, 0.4, "F.Fab"))
    if led:
        b.append(fpline(-1.6, -0.75, -1.6, 0.75, "F.SilkS"))  # cathode side
    b.append(fpline(-1.48, -0.75, 1.48, -0.75, "F.SilkS"))
    b.append(fpline(-1.48, 0.75, 1.48, 0.75, "F.SilkS"))
    b.append(fprect(-1.5, -0.9, 1.5, 0.9, "F.CrtYd", 0.05))
    if led:
        b.append(model(f"{KICAD3D}/LED_SMD.3dshapes/LED_0603_1608Metric.step"))
    else:
        b.append(model(f"{KICAD3D}/Resistor_SMD.3dshapes/R_0603_1608Metric.step"))
    return s + "\n".join(b) + "\n  )\n"

# ---- 0402 imperial (1005 metric) chip R/C/L -- IPC-nominal land pattern ----
# Used for the antenna-matching caps (C17/C18): the real Pico W reference
# parts (Murata GJM1555C1H series) are 0402, not the 0603 this file's other
# passives use -- a too-large pad here works electrically but doesn't match
# the real component footprint. VERIFY against the exact vendor's land
# pattern drawing before fab; these are generic IPC-nominal dimensions.
def fp_0402(ref, val, x, y, rot, path_uuid, n1, n2, side="F"):
    L = "B" if side == "B" else "F"
    s = fp_header("kbd:RC_0402", ref, val, x, y, rot, layer=f"{L}.Cu",
                  ref_at=(0, -1.1), path_uuid=path_uuid, val_at=(0, 1.1))
    b = []
    b.append(pad(1, "smd", "roundrect", -0.485, 0, 0.54, 0.64,
                 f'"{L}.Cu" "{L}.Paste" "{L}.Mask"', n1, rot=rot,
                 extra=" (roundrect_rratio 0.25)"))
    b.append(pad(2, "smd", "roundrect", 0.485, 0, 0.54, 0.64,
                 f'"{L}.Cu" "{L}.Paste" "{L}.Mask"', n2, rot=rot,
                 extra=" (roundrect_rratio 0.25)"))
    b.append(fprect(-0.5, -0.25, 0.5, 0.25, f"{L}.Fab"))
    b.append(fpline(-0.99, -0.55, 0.99, -0.55, f"{L}.SilkS"))
    b.append(fpline(-0.99, 0.55, 0.99, 0.55, f"{L}.SilkS"))
    b.append(fprect(-1.0, -0.6, 1.0, 0.6, f"{L}.CrtYd", 0.05))
    b.append(model(f"{KICAD3D}/Resistor_SMD.3dshapes/R_0402_1005Metric.step"))
    return s + "\n".join(b) + "\n  )\n"

# ---- 0201 imperial (0603 metric) chip R/C/L -- IPC-nominal land pattern ----
# Used for the antenna-matching inductor (L2): the real Pico W reference
# part (Cyntec CML0306-4N7-HNH, now obsolete; DigiKey's listed direct
# substitute is Murata LQP03TN4N7H02D) is this much smaller 0201 package,
# not the 0603 this file's other passives use. This is genuinely a
# reflow/stencil-only part -- not realistically hand-solderable. VERIFY
# against the exact vendor's land pattern drawing before fab.
def fp_0201(ref, val, x, y, rot, path_uuid, n1, n2):
    s = fp_header("kbd:RC_0201", ref, val, x, y, rot,
                  ref_at=(0, -0.7), path_uuid=path_uuid, val_at=(0, 0.7))
    b = []
    b.append(pad(1, "smd", "roundrect", -0.245, 0, 0.3, 0.25,
                 '"F.Cu" "F.Paste" "F.Mask"', n1, rot=rot,
                 extra=" (roundrect_rratio 0.25)"))
    b.append(pad(2, "smd", "roundrect", 0.245, 0, 0.3, 0.25,
                 '"F.Cu" "F.Paste" "F.Mask"', n2, rot=rot,
                 extra=" (roundrect_rratio 0.25)"))
    b.append(fprect(-0.3, -0.15, 0.3, 0.15, "F.Fab"))
    b.append(fpline(-0.61, -0.28, 0.61, -0.28, "F.SilkS"))
    b.append(fpline(-0.61, 0.28, 0.61, 0.28, "F.SilkS"))
    b.append(fprect(-0.61, -0.33, 0.61, 0.33, "F.CrtYd", 0.05))
    b.append(model(f"{KICAD3D}/Resistor_SMD.3dshapes/R_0201_0603Metric.step"))
    return s + "\n".join(b) + "\n  )\n"

def fp_jst_ph2(ref, x, y, rot, path_uuid, n1, n2):
    s = fp_header("kbd:JST_PH_S2B_2pin", ref, "Battery JST-PH", x, y, rot,
                  attr="through_hole", ref_at=(1.0, -4.6), path_uuid=path_uuid,
                  val_at=(1.0, 4.4))
    b = []
    b.append(f'    (pad "1" thru_hole roundrect (at -1 0 {rot:g}) (size 1.7 1.7) (drill 0.8) '
             f'(layers "*.Cu" "*.Mask") (roundrect_rratio 0.25) {net(n1)} (uuid "{U("jst1",ref)}"))')
    b.append(f'    (pad "2" thru_hole circle (at 1 0 {rot:g}) (size 1.7 1.7) (drill 0.8) '
             f'(layers "*.Cu" "*.Mask") {net(n2)} (uuid "{U("jst2",ref)}"))')
    b.append(fprect(-3.95, -1.7, 3.95, 3.4, "F.Fab"))
    b.append(fprect(-3.95, -1.7, 3.95, 3.4, "F.SilkS", 0.12))
    b.append(f'''    (fp_text user "+" (at -2.4 -2.6) (layer "F.SilkS") (uuid "{U('jsttxt',ref)}")
      (effects (font (size 1 1) (thickness 0.15))))''')
    b.append(fprect(-4.2, -2.0, 4.2, 3.7, "F.CrtYd", 0.05))
    return s + "\n".join(b) + "\n  )\n"

def fp_jst_sh(ref, x, y, rot, path_uuid, n1, n2):
    """JST SH SM02B-SRSS-TB horizontal, mounted on the BACK side.
    Official KiCad pad geometry, x-mirrored for back-side authoring.
    Cable exits toward +y (board interior)."""
    s = fp_header("kbd:JST_SH_SM02B_2pin_Back", ref, "Battery JST-SH", x, y, rot,
                  layer="B.Cu", attr="smd", ref_at=(0, -4.6), path_uuid=path_uuid,
                  val_at=(0, 4.4))
    b = []
    b.append(pad(1, "smd", "roundrect", 0.5, -2.0, 0.6, 1.55,
                 '"B.Cu" "B.Paste" "B.Mask"', n1, rot=rot,
                 extra=" (roundrect_rratio 0.25)"))
    b.append(pad(2, "smd", "roundrect", -0.5, -2.0, 0.6, 1.55,
                 '"B.Cu" "B.Paste" "B.Mask"', n2, rot=rot,
                 extra=" (roundrect_rratio 0.25)"))
    for mx in (-1.8, 1.8):
        b.append('    (pad "MP" smd roundrect (at %g 1.875 %g) (size 1.2 1.8) '
             '(layers "B.Cu" "B.Paste" "B.Mask") (roundrect_rratio 0.208333) '
             '(uuid "%s"))' % (mx, rot, NU("jstmp", ref, mx)))
    b.append(fprect(-2.0, -1.675, 2.0, 2.575, "B.Fab"))
    b.append(fpline(-2.11, 0.715, -2.11, -1.785, "B.SilkS"))
    b.append(fpline(2.11, 0.715, 2.11, -1.785, "B.SilkS"))
    b.append(fpline(-0.94, 2.685, 0.94, 2.685, "B.SilkS"))
    plus = '    (fp_text user "+" (at 1.7 -3.1) (layer "B.SilkS") (uuid "%s")\n'
    plus += '      (effects (font (size 1 1) (thickness 0.15)) (justify mirror)))'
    b.append(plus % NU("jsttxt", ref))
    b.append(fprect(-2.9, -3.28, 2.9, 3.28, "B.CrtYd", 0.05))
    b.append(model(f"{PROJ3D}/jst_sh_2p.wrl", scale=(2.54, 2.54, 2.54)))
    return s + "\n".join(b) + "\n  )\n"

def fp_slide(ref, x, y, rot, path_uuid, pinnet):
    s = fp_header("kbd:SW_Slide_MSK12C02", ref, "PWR MSK-12C02", x, y, rot,
                  ref_at=(0, -3.2), path_uuid=path_uuid, val_at=(0, 3.6))
    b = []
    for n, px in [(1, -2.5), (2, 0.0), (3, 2.5)]:
        b.append(pad(n, "smd", "rect", px, 2.0, 0.7, 1.6,
                     '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(n), rot=rot))
    for px in (-4.4, 4.4):
        b.append(f'    (pad "" smd rect (at {px:g} 0 {rot:g}) (size 1.2 2.4) '
                 f'(layers "F.Cu" "F.Paste" "F.Mask") (uuid "{NU("slm",ref,px)}"))')
    b.append(fprect(-4.5, -1.8, 4.5, 1.4, "F.Fab"))
    b.append(fpline(-4.5, -1.9, 4.5, -1.9, "F.SilkS"))
    b.append(fpline(0, -1.9, 0, -2.6, "F.SilkS"))        # lever exits board edge
    b.append(fpline(-0.5, -2.2, 0, -2.6, "F.SilkS"))
    b.append(fpline(0.5, -2.2, 0, -2.6, "F.SilkS"))
    b.append(fprect(-5.3, -2.9, 5.3, 3.1, "F.CrtYd", 0.05))
    b.append(model(f"{PROJ3D}/slide_msk12c02.wrl", scale=(2.54, 2.54, 2.54)))
    return s + "\n".join(b) + "\n  )\n"

def fp_btn6mm(ref, val, x, y, rot, path_uuid, n1, n2, side="F"):
    layer = "B.Cu" if side == "B" else "F.Cu"
    s = fp_header("kbd:SW_PUSH_6mm_THT", ref, val, x, y, rot, layer=layer,
                  attr="through_hole", ref_at=(0, -4.6), path_uuid=path_uuid,
                  val_at=(0, 4.6))
    b = []
    for px in (-3.25, 3.25):
        b.append(f'    (pad "1" thru_hole circle (at {px:g} -2.25 {rot:g}) (size 2 2) (drill 1.05) '
                 f'(layers "*.Cu" "*.Mask") {net(n1)} (uuid "{NU("btn1",ref,px)}"))')
        b.append(f'    (pad "2" thru_hole circle (at {px:g} 2.25 {rot:g}) (size 2 2) (drill 1.05) '
                 f'(layers "*.Cu" "*.Mask") {net(n2)} (uuid "{NU("btn2",ref,px)}"))')
    b.append(fprect(-3.0, -3.0, 3.0, 3.0, side + ".SilkS", 0.12))
    b.append(fprect(-3.0, -3.0, 3.0, 3.0, side + ".Fab"))
    b.append(fprect(-4.4, -3.5, 4.4, 3.5, side + ".CrtYd", 0.05))
    b.append(model(f"{KICAD3D}/Button_Switch_THT.3dshapes/SW_PUSH_6mm.step"))
    return s + "\n".join(b) + "\n  )\n"

# ---- 1mm fiducial: bare copper dot, 2mm mask opening -----------------------
# Pick-and-place vision targets. Required in practice for this board's
# assembly: U1 is a 0.4mm-pitch QFN-56 and U6 a 0.4mm-pitch WLBGA-63, and
# both sides carry SMD parts (hot-swap sockets, reverse-mount LEDs, diodes
# on B.Cu). Three per side, in an asymmetric triangle so the vision system
# can detect a flipped or rotated board.
def fp_fiducial(ref, x, y, path_uuid, side="F"):
    layer = "B" if side == "B" else "F"
    s = fp_header("kbd:FIDUCIAL_1MM", ref, "FIDUCIAL", x, y, 0,
                  layer=f"{layer}.Cu",
                  attr="smd exclude_from_pos_files exclude_from_bom",
                  ref_at=(0, -1.9), path_uuid=path_uuid, val_at=(0, 1.9))
    b = [pad(1, "smd", "circle", 0, 0, 1.0, 1.0,
             f'"{layer}.Cu" "{layer}.Mask"', None,
             extra=" (solder_mask_margin 0.5)"),
         fprect(-1.5, -1.5, 1.5, 1.5, f"{layer}.CrtYd", 0.05)]
    return s + "\n".join(b) + "\n  )\n"

def fp_hole(ref, x, y):
    # M2 clearance hole, "normal fit" per ISO 273 (2.4mm, vs. 2.2mm "close
    # fit" / 2.6mm "loose fit") -- close fit assumes precise alignment with
    # injection-molded mounting bosses; this board's case is 3D-printed,
    # which has looser dimensional tolerances, so normal fit is the safer
    # choice to avoid a boss binding against an undersized hole.
    s = fp_header("kbd:MountingHole_M2", ref, "M2", x, y, 0,
                  attr="exclude_from_pos_files exclude_from_bom",
                  ref_at=(0, -2.8), val_at=(0, 2.8))
    b = [npth(0, 0, 2.4),
         f'    (fp_circle (center 0 0) (end 2.3 0) (stroke (width 0.15) (type solid)) (fill none) (layer "F.SilkS") (uuid "{U("holec",ref)}"))',
         f'    (fp_circle (center 0 0) (end 2.4 0) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd") (uuid "{U("holecy",ref)}"))']
    return s + "\n".join(b) + "\n  )\n"

# ---- RP2040 (QFN-56, 7x7mm, 0.4mm pitch) -----------------------------------
# Side rotation now matches the real datasheet pinout diagram (Fig. 3):
# LEFT=1-14 (top->bottom), BOTTOM=15-28 (left->right), RIGHT=29-42
# (bottom->top), TOP=43-56 (right->left). An earlier version of this file
# had all four sides rotated by one position (e.g. treating 1-14 as the
# bottom side).
#
# Pad size: RPi's own "Recommended PCB Footprint" (RP2040 datasheet
# sec. 5.1.2, Fig. 167) specifies 0.20mm-wide pads at the 0.4mm pitch, not
# the 0.25mm generic IPC-nominal width this used to have. That 0.05mm
# matters: at 0.25mm width the gap between adjacent pads is only 0.15mm,
# below PCBWay's (and most fabs') 0.19mm minimum solder-mask-bridge
# clearance -- they can't put mask between the pads at that gap, meaning
# the whole row opens up as one exposed-copper slot. 0.20mm-wide pads
# (RPi's own number) leave a 0.20mm gap, just clearing the 0.19mm minimum.
def fp_rp2040(ref, x, y, path_uuid, pinnet):
    s = fp_header("kbd:RP2040_QFN56", ref, "RP2040", x, y, 0,
                  ref_at=(0, -4.5), path_uuid=path_uuid, val_at=(0, 4.8))
    b = []
    half_body = 3.5
    pad_len, pad_w = 0.6, 0.20
    pitch = 0.4
    n_side = 14
    offs = [(-((n_side - 1) / 2) + i) * pitch for i in range(n_side)]
    pin = 1
    # left side (pins 1-14), pads pointing left, numbered top->bottom
    for oy in offs:
        b.append(pad(pin, "smd", "rect", -(half_body + pad_len / 2 - 0.15), oy, pad_len, pad_w,
                     '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(pin)))
        pin += 1
    # bottom side (pins 15-28), pads pointing down, numbered left->right
    for ox in offs:
        b.append(pad(pin, "smd", "rect", ox, half_body + pad_len / 2 - 0.15, pad_w, pad_len,
                     '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(pin)))
        pin += 1
    # right side (pins 29-42), numbered bottom->top
    for oy in reversed(offs):
        b.append(pad(pin, "smd", "rect", half_body + pad_len / 2 - 0.15, oy, pad_len, pad_w,
                     '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(pin)))
        pin += 1
    # top side (pins 43-56), numbered right->left
    for ox in reversed(offs):
        b.append(pad(pin, "smd", "rect", ox, -(half_body + pad_len / 2 - 0.15), pad_w, pad_len,
                     '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(pin)))
        pin += 1
    # exposed thermal pad (VERIFY exact size against datasheet; ~5x5mm typical for this body)
    b.append(pad(57, "smd", "rect", 0, 0, 5.0, 5.0,
                 '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(57), extra=" (zone_connect 2)"))
    b.append(fprect(-3.5, -3.5, 3.5, 3.5, "F.Fab"))
    b.append(fprect(-4.2, -4.2, 4.2, 4.2, "F.CrtYd", 0.05))
    b.append(fpline(-3.9, -3.9, -3.2, -3.9, "F.SilkS"))
    b.append(fpline(-3.9, -3.9, -3.9, -3.2, "F.SilkS"))  # pin 1 corner mark
    # EP3.2x3.2mm variant matches the real RP2040's own exposed pad size,
    # not this footprint's own placeholder 5x5mm pad (see the comment on
    # that pad above) -- fine for visualization since the body/pin envelope
    # (7x7mm, 0.4mm pitch) is what's actually accurate here.
    b.append(model(f"{KICAD3D}/Package_DFN_QFN.3dshapes/"
                    "QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm.step"))
    return s + "\n".join(b) + "\n  )\n"

# ---- External QSPI NOR flash, small 8-pad package --------------------------
# VERIFY: package dims are a placeholder (approximating a small SOIC-8/
# USON-8 style land pattern); confirm against the exact flash MPN chosen.
def fp_flash8(ref, x, y, rot, path_uuid, pinnet):
    # Dimensions transcribed from the real Winbond W25Q16JV datasheet
    # (Section 11.4, "8-Pad USON 2x3x0.6-mm (Package Code UX)"): body
    # 3.00 x 2.00mm nominal (D x E), 0.5mm pin pitch, pad width 0.25mm (b),
    # pad length 0.45mm (L) -- not the placeholder dims an earlier version
    # of this file used (which were too small/wrong aspect ratio).
    s = fp_header("kbd:FLASH_USON8", ref, "W25Q16JVUXIQ", x, y, rot,
                  ref_at=(0, -2.2), path_uuid=path_uuid, val_at=(0, 2.2))
    b = []
    ys = [-0.75, -0.25, 0.25, 0.75]
    pad_len, pad_w = 0.45, 0.25
    pad_x = 1.275  # D/2 - pad_len/2 = 1.5 - 0.225
    for i, py in enumerate(ys, start=1):
        b.append(pad(i, "smd", "rect", -pad_x, py, pad_len, pad_w,
                     '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(i), rot=rot))
    for i, py in enumerate(reversed(ys), start=5):
        b.append(pad(i, "smd", "rect", pad_x, py, pad_len, pad_w,
                     '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(i), rot=rot))
    b.append(fprect(-1.5, -1.0, 1.5, 1.0, "F.Fab"))
    b.append(fpline(-1.8, -1.15, -1.0, -1.15, "F.SilkS"))
    b.append(fprect(-1.8, -1.3, 1.8, 1.3, "F.CrtYd", 0.05))
    # exact vendor match: real Winbond USON-8, 3x2mm body, 0.5mm pitch --
    # same package this footprint models.
    b.append(model(f"{KICAD3D}/Package_SON.3dshapes/"
                    "Winbond_USON-8-1EP_3x2mm_P0.5mm_EP0.2x1.6mm.step"))
    return s + "\n".join(b) + "\n  )\n"

# ---- 2-pin crystal, small SMD (e.g. 3.2x2.5mm) -----------------------------
def fp_crystal_smd(ref, val, x, y, rot, path_uuid, n1, n2):
    s = fp_header("kbd:XTAL_3225", ref, val, x, y, rot,
                  ref_at=(0, -2.0), path_uuid=path_uuid, val_at=(0, 2.0))
    b = []
    b.append(pad(1, "smd", "rect", -1.3, 0, 1.0, 1.4,
                 '"F.Cu" "F.Paste" "F.Mask"', n1, rot=rot))
    b.append(pad(2, "smd", "rect", 1.3, 0, 1.0, 1.4,
                 '"F.Cu" "F.Paste" "F.Mask"', n2, rot=rot))
    b.append(fprect(-1.6, -1.25, 1.6, 1.25, "F.Fab"))
    b.append(fprect(-1.9, -1.55, 1.9, 1.55, "F.CrtYd", 0.05))
    # 4-pin real crystal package vs. this footprint's simplified 2-pad
    # land pattern -- same 3.2x2.5mm body size, close enough for a 3D
    # preview even though the pad count doesn't match 1:1.
    b.append(model(f"{KICAD3D}/Crystal.3dshapes/"
                    "Crystal_SMD_3225-4Pin_3.2x2.5mm.step"))
    return s + "\n".join(b) + "\n  )\n"

# ---- Infineon CYW43439 wireless (WLBGA-63, 0.4mm ball pitch) --------------
# Ball designators, function names and X-Y coordinates (um, package center
# at 0,0) transcribed from the Infineon/Cypress CYW43439 datasheet
# (Document 002-30348 Rev *D), Table 14 "WLBGA Ball List -- Ordered By Ball
# Number" (datasheet states these X-Y values are for a TOP view). KiCad's
# footprint editor is Y-down for a top-side/F.Cu part, while the datasheet
# table follows the conventional Y-up drafting convention -- so each ball's
# KiCad y = -(datasheet y)/1000 (same Y-flip lesson learned the hard way on
# this file's schematic-symbol pins; see the U1 comment in build_schematic).
# Package body is ~2.4 x 4.4mm; 0.4mm pitch confirmed from adjacent-ball
# deltas in the table (e.g. A6->A7 = 1199.988-799.992 = 399.996um = 0.4mm).
CYW43439_BALLS = [
    ("A1", "BT_UART_RXD", -1200.006, 2199.996), ("A2", "BT_UART_TXD", -799.992, 2199.996),
    ("A5", "BT_PCM_CLK", 399.996, 2199.996), ("A6", "SR_VLX", 799.992, 2199.978),
    ("A7", "SR_PVSS", 1199.988, 2199.978),
    ("B1", "BT_DEV_WAKE", -1200.006, 1800), ("B2", "BT_UART_CTS_N", -799.992, 1800),
    ("B4", "BT_PCM_OUT", 0, 1800), ("B5", "BT_PCM_SYNC", 399.996, 1800),
    ("B6", "PMU_AVSS", 799.992, 1799.982), ("B7", "SR_VDDBAT5V", 1199.988, 1799.982),
    ("C1", "BT_HOST_WAKE", -1200.006, 1399.995), ("C2", "FM_OUT1", -799.992, 1399.986),
    ("C3", "BT_UART_RTS_N", -399.996, 1399.995), ("C4", "BT_PCM_IN", 0, 1399.995),
    ("C6", "VOUT_CLDO", 799.992, 1399.986), ("C7", "LDO_VDD1P5", 1199.988, 1399.986),
    ("D2", "FM_OUT2", -799.992, 999.99), ("D3", "VDDC", -399.996, 999.999),
    ("D4", "VSSC", 0, 999.999), ("D6", "VOUT_LNLDO", 799.992, 999.99),
    ("E1", "FM_RF_IN", -1199.988, 599.994), ("E2", "FM_RF_VDD", -799.992, 599.994),
    ("E3", "FM_RF_VSS", -399.996, 599.994), ("E6", "BT_REG_ON", 799.992, 599.994),
    ("E7", "VOUT_3P3", 1199.988, 599.994),
    ("F1", "BT_VCO_VDD", -1199.988, 199.998), ("F2", "BTFM_PLL_VDD", -799.992, 199.998),
    ("F5", "LPO_IN", 399.996, 199.998), ("F6", "WCC_VDDIO", 800.001, 199.998),
    ("F7", "LDO_VDDBAT5V", 1199.988, 199.998),
    ("G1", "BT_IF_VDD", -1199.988, -199.998), ("G2", "BTFM_PLL_VSS", -799.992, -199.998),
    ("G4", "VDDC", 0, -199.998), ("G6", "WL_REG_ON", 800.001, -199.998),
    ("H1", "BT_PAVDD", -1199.988, -599.994), ("H2", "BT_IF_VSS", -799.992, -599.994),
    ("H3", "BT_VCO_VSS", -399.996, -599.994), ("H4", "WLRF_AFE_GND", 0, -599.994),
    ("H6", "GPIO_1", 800.001, -599.994), ("H7", "SDIO_DATA_1", 1200.006, -599.994),
    ("J1", "WLRF_2G_eLG", -1199.988, -999.99), ("J2", "WLRF_LNA_GND", -799.992, -999.99),
    ("J3", "WLRF_GPIO", -399.996, -999.99), ("J5", "VSSC", 399.996, -999.999),
    ("J6", "GPIO_0", 800.001, -999.999), ("J7", "SDIO_DATA_3", 1200.006, -999.999),
    ("K1", "WLRF_2G_RF", -1199.988, -1399.986), ("K2", "WLRF_GENERAL_GND", -799.992, -1399.986),
    ("K6", "SDIO_DATA_0", 800.001, -1399.995),
    ("L2", "WLRF_PA_GND", -799.992, -1799.982), ("L3", "WLRF_VCO_GND", -399.996, -1799.982),
    ("L4", "WLRF_XTAL_GND", 0, -1799.982), ("L5", "GPIO_2", 399.996, -1799.991),
    ("L6", "SDIO_CMD", 800.001, -1799.991), ("L7", "SDIO_DATA_2", 1200.006, -1799.991),
    ("M1", "WLRF_PA_VDD", -1199.988, -2199.978), ("M2", "WLRF_VDD_1P35", -799.992, -2199.978),
    ("M3", "WLRF_XTAL_VDD1P2", -399.996, -2199.978), ("M4", "WLRF_XTAL_XOP", 0, -2199.978),
    ("M5", "WLRF_XTAL_XON", 399.996, -2199.978), ("M6", "CLK_REQ", 800.001, -2199.996),
    ("M7", "SDIO_CLK", 1200.006, -2199.996),
]
assert len(CYW43439_BALLS) == 63

# Ball-function-name -> net-name for this BLE-only variant. WLAN is
# permanently held in reset (WL_REG_ON -> GND), so the SDIO/gSPI bus, WLAN
# GPIOs, and the FM-radio front end are all left unconnected (NC); Bluetooth
# runs over its own dedicated UART (sec. 9.2), not that bus. VDDC/VOUT_CLDO
# and LDO_VDD1P5/WLRF_VDD_1P35 are the same internal node in each pair per
# datasheet Figure 3 (shown as one continuous trace with only decoupling
# caps in between) -- tied to a single net accordingly.
CYW_BALLNET = {
    "BT_UART_RXD": "BT_UART_RXD", "BT_UART_TXD": "BT_UART_TXD",
    "BT_UART_CTS_N": "BT_UART_CTS_N", "BT_UART_RTS_N": "BT_UART_RTS_N",
    "BT_DEV_WAKE": "BT_DEV_WAKE", "BT_HOST_WAKE": "BT_HOST_WAKE",
    "BT_REG_ON": "BT_REG_ON",
    "SR_VLX": "CYW_SR_VLX", "LDO_VDD1P5": "CYW_VDD1P5", "WLRF_VDD_1P35": "CYW_VDD1P5",
    "WLRF_XTAL_VDD1P2": "CYW_XTAL_VDD1P2",
    "VOUT_CLDO": "CYW_VOUT_CLDO", "VDDC": "CYW_VOUT_CLDO",
    "VOUT_LNLDO": "CYW_VOUT_LNLDO", "VOUT_3P3": "CYW_VOUT_3P3",
    "WLRF_PA_VDD": "CYW_PA_VDD", "BT_PAVDD": "CYW_PA_VDD",
    "BT_VCO_VDD": "CYW_BT_VCO_VDD", "BTFM_PLL_VDD": "CYW_BTFM_PLL_VDD",
    "BT_IF_VDD": "CYW_BT_IF_VDD",
    "WCC_VDDIO": "+3V3", "SR_VDDBAT5V": "VSYS", "LDO_VDDBAT5V": "VSYS",
    "WLRF_2G_RF": "WLRF_ANT",
    "WLRF_XTAL_XOP": "CYW_XTAL_XOP", "WLRF_XTAL_XON": "CYW_XTAL_XON",
    "WL_REG_ON": "GND",       # WLAN section permanently disabled (BLE-only board)
    "LPO_IN": "GND",          # use the internal ~33kHz LPO, no external 32.768kHz xtal
    "SR_PVSS": "GND", "PMU_AVSS": "GND", "VSSC": "GND",
    "WLRF_AFE_GND": "GND", "WLRF_LNA_GND": "GND", "WLRF_GENERAL_GND": "GND",
    "WLRF_PA_GND": "GND", "WLRF_VCO_GND": "GND", "WLRF_XTAL_GND": "GND",
    "BT_IF_VSS": "GND", "BT_VCO_VSS": "GND", "BTFM_PLL_VSS": "GND",
    # unused-feature signal/GPIO pins (WLAN SDIO/gSPI bus + WLAN GPIOs, FM
    # radio front end, BT PCM audio interface) -- left no-connect.
    "FM_OUT1": None, "FM_OUT2": None, "FM_RF_IN": None, "FM_RF_VDD": None, "FM_RF_VSS": None,
    "BT_PCM_CLK": None, "BT_PCM_OUT": None, "BT_PCM_SYNC": None, "BT_PCM_IN": None,
    "GPIO_0": None, "GPIO_1": None, "GPIO_2": None, "WLRF_2G_eLG": None, "WLRF_GPIO": None,
    "SDIO_DATA_0": None, "SDIO_DATA_1": None, "SDIO_DATA_2": None, "SDIO_DATA_3": None,
    "SDIO_CMD": None, "SDIO_CLK": None, "CLK_REQ": None,
}
assert set(b[1] for b in CYW43439_BALLS) == set(CYW_BALLNET.keys())

def cyw_pinnet():
    """ball designator ("A1", "M7", ...) -> net name, for the PCB footprint."""
    return {desig: CYW_BALLNET[func] for (desig, func, _x, _y) in CYW43439_BALLS}

def fp_cyw43439(ref, x, y, path_uuid, pinnet):
    """pinnet: ball designator -> net name (see cyw_pinnet()).
    VERIFY: pad shape/size (0.25mm circular NSMD) is a generic 0.4mm-pitch
    WLBGA convention, not copied from an Infineon land-pattern drawing --
    this fine-pitch BGA also requires professional stencil/reflow assembly,
    it is not hand-solderable."""
    s = fp_header("kbd:CYW43439_WLBGA63", ref, "CYW43439", x, y, 0,
                  ref_at=(0, -2.6), path_uuid=path_uuid, val_at=(0, 2.6))
    b = []
    pad_dia = 0.25
    for (desig, _func, xu, yu) in CYW43439_BALLS:
        kx, ky = xu / 1000.0, -yu / 1000.0
        b.append(pad(desig, "smd", "circle", kx, ky, pad_dia, pad_dia,
                     '"F.Cu" "F.Paste" "F.Mask"', pinnet.get(desig)))
    b.append(fprect(-1.2, -2.2, 1.2, 2.2, "F.Fab"))
    b.append(fprect(-1.45, -2.45, 1.45, 2.45, "F.CrtYd", 0.05))
    b.append(fpline(-1.35, -2.35, -0.6, -2.35, "F.SilkS"))
    b.append(f'''    (fp_text user "WLBGA-63 0.4mm pitch -- reflow/stencil assembly required" (at 0 2.9) (layer "F.SilkS") (uuid "{U('cywtxt',ref)}")
      (effects (font (size 0.5 0.5) (thickness 0.08))))''')
    return s + "\n".join(b) + "\n  )\n"

# ---- SK6812MINI-E per-key RGB LED (4-pad: VDD, DOUT, GND, DIN) -------------
def fp_sk6812mini(ref, x, y, rot, path_uuid, pinnet):
    # Transcribed directly from KiCad 10's own standard library footprint
    # (LED_SMD.pretty/LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount.kicad_mod),
    # placed exactly as KiCad's own footprint editor places it for back-side
    # reverse mounting: layer B.Cu, footprint rotation +180 on top of the
    # native F.Cu pad layout (mirroring is implicit in the stored B.Cu pad
    # coordinates below, not something this code computes). Net-to-pad-number
    # mapping (1=GND, 2=DOUT, 3=VDD, 4=DIN) is the real part's own physical
    # layout, cross-checked against a real board reference using this exact
    # footprint (see LED_CHAIN_48/49 nets on pads 4/2 respectively -- pad 4
    # takes the incoming link from the previous LED, pad 2 sends the
    # outgoing link to the next one).
    #
    # The Edge.Cuts geometry below is the library's own purpose-built
    # light-transmission cutout for this exact reverse-mount application --
    # not a plain round hole -- so it's copied verbatim rather than
    # approximated. It's bilaterally symmetric on both axes, so it renders
    # identically regardless of the mirror/rotation applied to the pads.
    s = fp_header("kbd:SK6812MINI_E", ref, "SK6812MINI-E", x, y,
                  (rot + 180) % 360, layer="B.Cu", attr="smd",
                  ref_at=(0, 2.6), val_at=(0, -2.54), path_uuid=path_uuid)
    b = []
    corners = [(1, -2.725, -0.75), (2, -2.725, 0.75), (3, 2.725, 0.75), (4, 2.725, -0.75)]
    for n, px, py in corners:
        b.append(pad(n, "smd", "roundrect", px, py, 1.35, 0.82,
                     '"B.Cu" "B.Mask" "B.Paste"', pinnet.get(n), rot=rot,
                     extra=" (roundrect_rratio 0.25)"))
    for x1, y1, x2, y2 in [(3.65, 1.875, 3.65, -1.875), (3.65, -1.875, -2.925, -1.875),
                           (-3.65, 1.875, 3.65, 1.875), (-3.65, -1.15, -2.925, -1.875),
                           (-3.65, -1.15, -3.65, 1.875)]:
        b.append(fpline(x1, y1, x2, y2, "B.SilkS"))
    b.append(f'    (fp_poly (pts (xy -2.725 -1.45) (xy -2.575 -1.65) (xy -2.875 -1.65)) '
             f'(stroke (width 0.12) (type solid)) (fill yes) (layer "B.SilkS") '
             f'(uuid "{NU("ledpoly",ref)}"))')
    for x1, y1, x2, y2 in [(1.7, 0, 1.7, 0.700353), (1.7, 0, 1.7, -0.700353),
                           (0, 1.5, 0.900353, 1.5), (0, 1.5, -0.900353, 1.5),
                           (0, -1.5, 0.900353, -1.5), (0, -1.5, -0.900353, -1.5),
                           (-1.7, 0, -1.7, 0.700353), (-1.7, 0, -1.7, -0.700353)]:
        b.append(fpline(x1, y1, x2, y2, "Edge.Cuts"))
    for sx, sy, mx, my, ex, ey in [
        (1.743934, 0.856655, 1.711191, 0.781533, 1.7, 0.700353),
        (1.743934, 0.856655, 1.670713, 1.470713, 1.056655, 1.543934),
        (1.7, -0.700353, 1.711181, -0.781538, 1.743934, -0.856655),
        (1.056655, -1.543934, 1.670711, -1.470711, 1.743934, -0.856655),
        (1.056655, -1.543934, 0.981533, -1.511191, 0.900353, -1.5),
        (0.900353, 1.5, 0.981532, 1.511193, 1.056655, 1.543934),
        (-0.900353, -1.5, -0.981533, -1.511192, -1.056655, -1.543934),
        (-1.056655, 1.543934, -0.981533, 1.511192, -0.900353, 1.5),
        (-1.056655, 1.543934, -1.670711, 1.470711, -1.743934, 0.856655),
        (-1.7, 0.700353, -1.711192, 0.781533, -1.743934, 0.856655),
        (-1.743934, -0.856655, -1.670711, -1.470711, -1.056655, -1.543934),
        (-1.743934, -0.856655, -1.711192, -0.781533, -1.7, -0.700353),
    ]:
        b.append(fparc(sx, sy, mx, my, ex, ey, "Edge.Cuts"))
    b.append(fprect(-3.65, 1.87, 3.65, -1.87, "B.CrtYd", 0.05))
    b.append(fpline(-0.8, -1.4, -1.6, -0.6, "B.Fab"))
    b.append(fprect(-1.6, 1.4, 1.6, -1.4, "B.Fab"))
    b.append(model(f"{KICAD3D}/LED_SMD.3dshapes/"
                    "LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount.step"))
    return s + "\n".join(b) + "\n  )\n"

# ---- Johanson 2450AT18B100E, 2.4GHz SMT chip antenna -----------------------
# Real, purchasable part (Johanson Technology datasheet, Ver. 4.0, 2018):
# 2400-2500MHz, 50 ohm, 0.5dBi peak gain, 2-terminal (1=FEED, 2=NC). Body
# L=3.20mm x W=1.60mm x T=1.30mm, terminal width "a"=0.50mm. Added because
# an earlier version of this file had an antenna KEEPOUT zone but no actual
# antenna connected to it -- WLRF_ANT_MID dead-ended at the (DNP) matching
# cap with nothing beyond it. VERIFY: exact pad length/placement is a
# reasonable IPC-style estimate from the body dims, not a copied land-
# pattern drawing (Johanson's own datasheet doesn't publish one -- it
# offers a free layout review instead, which is worth using before fab).
def fp_antenna_johanson(ref, x, y, rot, path_uuid, n_feed):
    s = fp_header("kbd:ANT_JOHANSON_2450AT18B100", ref, "2450AT18B100E", x, y, rot,
                  ref_at=(0, -1.3), path_uuid=path_uuid, val_at=(0, 1.3))
    b = []
    b.append(pad(1, "smd", "rect", -1.35, 0, 0.7, 1.4,
                 '"F.Cu" "F.Paste" "F.Mask"', n_feed, rot=rot))
    b.append(pad(2, "smd", "rect", 1.35, 0, 0.7, 1.4,
                 '"F.Cu" "F.Paste" "F.Mask"', None, rot=rot))  # NC per datasheet
    b.append(fprect(-1.6, -0.8, 1.6, 0.8, "F.Fab"))
    b.append(fpline(-1.9, -1.0, -1.3, -1.0, "F.SilkS"))  # pin 1 (FEED) mark
    b.append(fprect(-1.9, -1.05, 1.9, 1.05, "F.CrtYd", 0.05))
    b.append(model(f"{KICAD3D}/RF_Antenna.3dshapes/Johanson_2450AT18x100.step"))
    return s + "\n".join(b) + "\n  )\n"

# ============================================================ SCHEMATIC ====
GRID = 1.27
def g(v):   # snap-assert to schematic grid
    assert abs(v / GRID - round(v / GRID)) < 1e-6, f"off grid: {v}"
    return f"{v:g}"

FONT = "(effects (font (size 1.27 1.27)))"

def sch_wire(x1, y1, x2, y2):
    return (f'  (wire (pts (xy {g(x1)} {g(y1)}) (xy {g(x2)} {g(y2)})) '
            f'(stroke (width 0) (type default)) (uuid "{NU("w")}"))')

def sch_glabel(name, x, y, rot, shape="bidirectional"):
    just = {0: "left", 180: "right", 90: "left", 270: "right"}[rot]
    return f'''  (global_label "{name}" (shape {shape}) (at {g(x)} {g(y)} {rot}) (fields_autoplaced yes)
    (effects (font (size 1.27 1.27)) (justify {just}))
    (uuid "{NU("gl", name)}")
    (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {g(x)} {g(y)} 0)
      (effects (font (size 1.27 1.27)) (hide yes)))
  )'''

def sch_nc(x, y):
    return f'  (no_connect (at {g(x)} {g(y)}) (uuid "{NU("nc")}"))'

def sch_text(txt, x, y, size=2.54):
    return (f'  (text "{txt}" (exclude_from_sim no) (at {g(x)} {g(y)} 0) '
            f'(effects (font (size {size} {size}) (thickness 0.3) bold) (justify left bottom)) (uuid "{NU("t")}"))')

def sym_pin(ptype, x, y, rot, name, number, length=2.54, hide=False):
    h = " hide" if hide else ""
    return f'''      (pin {ptype} line (at {g(x)} {g(y)} {rot}) (length {length:g}){h}
        (name "{name}" {FONT})
        (number "{number}" {FONT})
      )'''

# ---- library symbols -------------------------------------------------------
def lib_header(name, refpfx, value, hide_pin_names=True, hide_pin_numbers=False):
    pn = "(pin_numbers hide) " if hide_pin_numbers else ""
    pnames = "(pin_names (offset 0.254) hide)" if hide_pin_names else "(pin_names (offset 0.254))"
    return f'''    (symbol "kbd:{name}" {pn}{pnames} (exclude_from_sim no) (in_bom yes) (on_board yes)
      (property "Reference" "{refpfx}" (at 0 2.54 0) {FONT})
      (property "Value" "{value}" (at 0 -2.54 0) {FONT})
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
'''

def simple_box_sym(name, refpfx, value, w, pins, extras=""):
    """pins: list of (ptype, x, y, rot, pname, pnum, hide)"""
    s = lib_header(name, refpfx, value)
    s += f'''      (symbol "{name}_0_1"
        (rectangle (start {g(-w/2)} {g(pins_top(pins))}) (end {g(w/2)} {g(pins_bot(pins))})
          (stroke (width 0.254) (type default)) (fill (type background)))
{extras}      )
      (symbol "{name}_1_1"
'''
    for (pt, x, y, rot, pn, num, hide) in pins:
        s += sym_pin(pt, x, y, rot, pn, num, hide=hide) + "\n"
    s += "      )\n    )\n"
    return s

def pins_top(pins):
    return max(p[2] for p in pins) - 0.0 + 2.54
def pins_bot(pins):
    return min(p[2] for p in pins) - 2.54

def two_pin_sym(name, refpfx, value, body):
    s = lib_header(name, refpfx, value)
    s += f'      (symbol "{name}_0_1"\n{body}      )\n'
    s += f'      (symbol "{name}_1_1"\n'
    s += sym_pin("passive", -3.81, 0, 0, "1", "1", length=1.27) + "\n"
    s += sym_pin("passive", 3.81, 0, 180, "2", "2", length=1.27) + "\n"
    s += "      )\n    )\n"
    return s

def build_lib_symbols():
    L = []
    # --- switch ---
    body = ('        (circle (center -1.27 0) (radius 0.508) (stroke (width 0) (type default)) (fill (type none)))\n'
            '        (circle (center 1.27 0) (radius 0.508) (stroke (width 0) (type default)) (fill (type none)))\n'
            '        (polyline (pts (xy -1.27 0.254) (xy 1.905 2.286)) (stroke (width 0) (type default)) (fill (type none)))\n')
    s = lib_header("SW_Push", "SW", "SW_Push")
    s += f'      (symbol "SW_Push_0_1"\n{body}      )\n      (symbol "SW_Push_1_1"\n'
    s += sym_pin("passive", -2.54, 0, 0, "1", "1", length=1.27) + "\n"
    s += sym_pin("passive", 2.54, 0, 180, "2", "2", length=1.27) + "\n"
    s += "      )\n    )\n"
    L.append(s)
    # --- diode (pin1=K left, pin2=A right) ---
    body = ('        (polyline (pts (xy -1.27 1.27) (xy -1.27 -1.27)) (stroke (width 0.254) (type default)) (fill (type none)))\n'
            '        (polyline (pts (xy 1.27 1.27) (xy 1.27 -1.27) (xy -1.27 0) (xy 1.27 1.27)) (stroke (width 0.254) (type default)) (fill (type outline)))\n')
    L.append(two_pin_sym("D_kbd", "D", "1N4148W", body))
    # --- schottky ---
    body = ('        (polyline (pts (xy -1.27 1.27) (xy -1.27 -1.27)) (stroke (width 0.254) (type default)) (fill (type none)))\n'
            '        (polyline (pts (xy -1.27 1.27) (xy -1.905 1.27) (xy -1.905 0.635)) (stroke (width 0.254) (type default)) (fill (type none)))\n'
            '        (polyline (pts (xy 1.27 1.27) (xy 1.27 -1.27) (xy -1.27 0) (xy 1.27 1.27)) (stroke (width 0.254) (type default)) (fill (type outline)))\n')
    L.append(two_pin_sym("D_Schottky_kbd", "D", "B5819W", body))
    # --- R ---
    body = '        (rectangle (start -2.54 1.016) (end 2.54 -1.016) (stroke (width 0.254) (type default)) (fill (type none)))\n'
    L.append(two_pin_sym("R_kbd", "R", "R", body))
    # --- C ---
    body = ('        (polyline (pts (xy -0.508 1.905) (xy -0.508 -1.905)) (stroke (width 0.508) (type default)) (fill (type none)))\n'
            '        (polyline (pts (xy 0.508 1.905) (xy 0.508 -1.905)) (stroke (width 0.508) (type default)) (fill (type none)))\n')
    s = lib_header("C_kbd", "C", "C")
    s += f'      (symbol "C_kbd_0_1"\n{body}      )\n      (symbol "C_kbd_1_1"\n'
    s += sym_pin("passive", -3.81, 0, 0, "1", "1", length=3.302) + "\n"
    s += sym_pin("passive", 3.81, 0, 180, "2", "2", length=3.302) + "\n"
    s += "      )\n    )\n"
    L.append(s)
    # --- LED (pin1=K left) ---
    body = ('        (polyline (pts (xy -1.27 1.27) (xy -1.27 -1.27)) (stroke (width 0.254) (type default)) (fill (type none)))\n'
            '        (polyline (pts (xy 1.27 1.27) (xy 1.27 -1.27) (xy -1.27 0) (xy 1.27 1.27)) (stroke (width 0.254) (type default)) (fill (type outline)))\n'
            '        (polyline (pts (xy 0 2.54) (xy 1.016 3.556)) (stroke (width 0.1524) (type default)) (fill (type none)))\n')
    L.append(two_pin_sym("LED_kbd", "D", "LED", body))
    # --- ESP32-C6-MINI-1 ---
    pins = []
    left_io = [("EN", 8), ("IO0", 12), ("IO1", 13), ("IO2", 5), ("IO3", 6),
               ("IO4", 9), ("IO5", 10), ("IO6", 15), ("IO7", 16), ("IO8", 22),
               ("IO9", 23), ("IO12/USB_D-", 17), ("IO13/USB_D+", 18),
               ("IO14", 19), ("IO15", 20)]
    y = 17.78
    for nm, num in left_io:
        pins.append(("bidirectional", -20.32, y, 0, nm, str(num), False))
        y -= 2.54
    right_io = [("TXD0/IO16", 31), ("RXD0/IO17", 30), ("IO18", 24), ("IO19", 25),
                ("IO20", 26), ("IO21", 27), ("IO22", 28), ("IO23", 29)]
    y = 17.78
    for nm, num in right_io:
        pins.append(("bidirectional", 20.32, y, 180, nm, str(num), False))
        y -= 2.54
    pins.append(("power_in", 0, 25.4, 270, "3V3", "3", False))
    pins.append(("power_in", 0, -25.4, 90, "GND", "1", False))
    for gnum in [2, 11, 14] + list(range(36, 54)) + [49]:
        pins.append(("power_in", 0, -25.4, 90, "GND", str(gnum), True))
    ncx = -8.89
    for ncnum in [4, 7, 21, 32, 33, 34, 35]:
        pins.append(("no_connect", ncx, 19.05, 270, "NC", str(ncnum), True))
        ncx += 2.54
    s = lib_header("ESP32-C6-MINI-1", "U", "ESP32-C6-MINI-1", hide_pin_names=False)
    s += f'''      (symbol "ESP32-C6-MINI-1_0_1"
        (rectangle (start -17.78 22.86) (end 17.78 -22.86)
          (stroke (width 0.254) (type default)) (fill (type background)))
      )
      (symbol "ESP32-C6-MINI-1_1_1"
'''
    for (pt, x, yy, rot, pn, num, hide) in pins:
        s += sym_pin(pt, x, yy, rot, pn, num, hide=hide) + "\n"
    s += "      )\n    )\n"
    L.append(s)

    def boxsym(name, refpfx, value, w, pinlist):
        s = lib_header(name, refpfx, value, hide_pin_names=False)
        top = max(p[2] for p in pinlist) + 2.54
        bot = min(p[2] for p in pinlist) - 2.54
        s += f'''      (symbol "{name}_0_1"
        (rectangle (start {g(-w/2)} {g(top)}) (end {g(w/2)} {g(bot)})
          (stroke (width 0.254) (type default)) (fill (type background)))
      )
      (symbol "{name}_1_1"
'''
        for (pt, x, yy, rot, pn, num) in pinlist:
            s += sym_pin(pt, x, yy, rot, pn, str(num)) + "\n"
        s += "      )\n    )\n"
        return s

    # --- RP2040 (QFN-56 chip-down) -- pins from RP2040_PINOUT, split
    # left/right (28 each) purely for schematic readability; physical pad
    # numbers on the footprint are unaffected by this schematic layout.
    rp_pins = []
    left_half = RP2040_PINOUT[:28]
    right_half = RP2040_PINOUT[28:]
    y = 2.54 * (len(left_half) - 1) / 2
    for (num, label, _net) in left_half:
        rp_pins.append(("bidirectional", -15.24, y, 0, label, num))
        y -= 2.54
    y = 2.54 * (len(right_half) - 1) / 2
    for (num, label, _net) in right_half:
        rp_pins.append(("bidirectional", 15.24, y, 180, label, num))
        y -= 2.54
    rp_pins.append(("power_in", 0, -2.54 * (len(left_half) / 2) - 2.54, 90, "EPAD", RP2040_THERMAL_PAD))
    L.append(boxsym("RP2040", "U", "RP2040 (VERIFY pinout before fab)", 30.48, rp_pins))

    # --- external QSPI flash (8-pin: CS, DO/IO1, WP/IO2, GND, DI/IO0, CLK, HOLD/IO3, VCC) ---
    L.append(boxsym("FLASH_QSPI", "U", "W25Q16JVUXIQ", 15.24, [
        ("passive", -10.16, 3.81, 0, "CS", 1),
        ("passive", -10.16, 1.27, 0, "DO/IO1", 2),
        ("passive", -10.16, -1.27, 0, "WP/IO2", 3),
        ("power_in", -10.16, -3.81, 0, "GND", 4),
        ("passive", 10.16, -3.81, 180, "DI/IO0", 5),
        ("passive", 10.16, -1.27, 180, "CLK", 6),
        ("passive", 10.16, 1.27, 180, "HOLD/IO3", 7),
        ("power_in", 10.16, 3.81, 180, "VCC", 8)]))

    # --- 2-pin crystal ---
    body = ('        (rectangle (start -2.032 1.27) (end 2.032 -1.27) '
            '(stroke (width 0.254) (type default)) (fill (type none)))\n')
    L.append(two_pin_sym("XTAL", "Y", "12MHz", body))

    # --- CYW43439 wireless (WLBGA-63, BLE via dedicated UART) ---
    # Only the balls this BLE-only variant actually uses get schematic pins
    # (the footprint still has all 63 physical balls -- see fp_cyw43439);
    # ball designators are used as pin numbers so symbol and footprint can't
    # drift apart, matching the datasheet's own ball naming.
    L.append(boxsym("CYW43439_WLBGA63", "U", "CYW43439", 30.48, [
        ("output", -12.7, 15.24, 0, "BT_UART_TXD", "A2"),
        ("input", -12.7, 12.7, 0, "BT_UART_RXD", "A1"),
        ("output", -12.7, 10.16, 0, "BT_UART_RTS_N", "C3"),
        ("input", -12.7, 7.62, 0, "BT_UART_CTS_N", "B2"),
        ("input", -12.7, 5.08, 0, "BT_REG_ON", "E6"),
        ("input", -12.7, 2.54, 0, "BT_DEV_WAKE", "B1"),
        ("output", -12.7, 0, 0, "BT_HOST_WAKE", "C1"),
        ("input", -12.7, -2.54, 0, "WL_REG_ON", "G6"),
        ("passive", -12.7, -5.08, 0, "XTAL_XOP", "M4"),
        ("passive", -12.7, -7.62, 0, "XTAL_XON", "M5"),
        ("output", -12.7, -10.16, 0, "ANT", "K1"),
        ("passive", -12.7, -12.7, 0, "BT_VCO_VDD", "F1"),      # internal LDO bypass, not fed externally
        ("passive", -12.7, -15.24, 0, "BTFM_PLL_VDD", "F2"),
        ("passive", 12.7, 15.24, 180, "SR_VLX", "A6"),          # buck switching node -> inductor, not power_in
        ("power_out", 12.7, 12.7, 180, "VDD1P5", "C7"),
        ("power_out", 12.7, 10.16, 180, "VDD1P35", "M2"),
        ("power_out", 12.7, 7.62, 180, "XTAL_VDD1P2", "M3"),
        ("power_out", 12.7, 5.08, 180, "VOUT_CLDO", "C6"),
        ("power_out", 12.7, 2.54, 180, "VOUT_LNLDO", "D6"),
        ("power_out", 12.7, 0, 180, "VOUT_3P3", "E7"),
        ("power_out", 12.7, -2.54, 180, "PA_VDD", "M1"),
        ("power_out", 12.7, -5.08, 180, "BT_PAVDD", "H1"),
        ("power_in", 12.7, -7.62, 180, "VDDIO", "F6"),
        ("power_in", 12.7, -10.16, 180, "VBAT", "B7"),
        ("power_in", 12.7, -12.7, 180, "VBAT2", "F7"),
        ("passive", 12.7, -15.24, 180, "BT_IF_VDD", "G1"),
        ("power_in", 0, -20.32, 90, "GND", "D4")]))

    # --- single-gate level shifter/buffer, SOT-23-5: TI SN74AHCT1G125DBVR
    # specifically (not, e.g., Nexperia's 74AHCT1G125, which is real but
    # doesn't come in SOT-23-5 at all -- only TSSOP5/SC-74A/XSON6/XSON5 --
    # and specs a narrower 4.5-5.5V VCC range). TI's part is confirmed real
    # (datasheet SCLS504E) in the DBV=SOT-23-5 package with the exact
    # OE/A/GND/Y/VCC pinout below, AND specs a 3-5.5V operating range that
    # comfortably covers this design's VCC source (VSYS, the unregulated
    # battery/USB rail, which can be as low as ~3.0V on battery) --
    # Nexperia's part would be out of its guaranteed VCC range there.
    # 1 OE(active-low, tie GND=enabled) 2 A(in) 3 GND 4 Y(out) 5 VCC
    L.append(boxsym("LVL_SHIFT_BUF", "U", "SN74AHCT1G125DBVR", 15.24, [
        ("input", -10.16, 2.54, 0, "OE#", 1),
        ("input", -10.16, 0, 0, "A", 2),
        ("power_in", -10.16, -2.54, 0, "GND", 3),
        ("output", 10.16, 0, 180, "Y", 4),
        ("power_in", 10.16, 2.54, 180, "VCC", 5)]))

    # --- SK6812MINI-E RGB LED (4-pin: VDD, DOUT, GND, DIN) ---
    L.append(boxsym("SK6812MINI", "D", "SK6812MINI-E", 12.7, [
        ("power_in", -8.89, 2.54, 0, "DIN", 4),
        ("power_in", -8.89, -2.54, 0, "GND", 3),
        ("output", 8.89, 2.54, 180, "DOUT", 2),
        ("power_in", 8.89, -2.54, 180, "VDD", 1)]))
    # --- 2.4GHz chip antenna (Johanson 2450AT18B100E): 1=FEED, 2=NC ---
    L.append(boxsym("ANT_JOHANSON", "ANT", "2450AT18B100E", 10.16, [
        ("input", -6.35, 0, 0, "FEED", 1),
        ("no_connect", 6.35, 0, 180, "NC", 2)]))

    # --- MCP73831 (SOT-23-5): 1 STAT 2 VSS 3 VBAT 4 VDD 5 PROG ---
    L.append(boxsym("MCP73831", "U", "MCP73831-2ACI/OT", 15.24, [
        ("power_in", -10.16, 2.54, 0, "VDD", 4),
        ("power_in", -10.16, -2.54, 0, "VSS", 2),
        ("power_out", 10.16, 2.54, 180, "VBAT", 3),
        ("open_collector", 10.16, 0, 180, "STAT", 1),
        ("passive", 10.16, -2.54, 180, "PROG", 5)]))
    # --- AP2112K-3.3: 1 VIN 2 GND 3 EN 4 NC 5 VOUT ---
    L.append(boxsym("AP2112K-3.3", "U", "AP2112K-3.3", 15.24, [
        ("power_in", -10.16, 2.54, 0, "VIN", 1),
        ("input", -10.16, 0, 0, "EN", 3),
        ("power_in", -10.16, -2.54, 0, "GND", 2),
        ("power_out", 10.16, 2.54, 180, "VOUT", 5),
        ("no_connect", 10.16, -2.54, 180, "NC", 4)]))
    # --- P-MOSFET DMG3415U: 1 G 2 S 3 D ---
    L.append(boxsym("Q_PMOS_GSD", "Q", "DMG3415U", 10.16, [
        ("input", -7.62, 0, 0, "G", 1),
        ("passive", 0, 5.08, 270, "S", 2),
        ("passive", 0, -5.08, 90, "D", 3)]))
    # --- USBLC6-2SC6 ---
    L.append(boxsym("USBLC6-2SC6", "U", "USBLC6-2SC6", 12.7, [
        ("passive", -8.89, 2.54, 0, "IO1", 1),
        ("power_in", -8.89, 0, 0, "GND", 2),
        ("passive", -8.89, -2.54, 0, "IO2", 3),
        ("passive", 8.89, 2.54, 180, "IO2", 4),
        ("power_in", 8.89, 0, 180, "VBUS", 5),
        ("passive", 8.89, -2.54, 180, "IO1", 6)]))
    # --- USB-C connector ---
    upins = [("passive", 13.97, 12.7, 180, "VBUS", "A4"),
             ("passive", 13.97, 10.16, 180, "VBUS", "B9"),
             ("passive", 13.97, 7.62, 180, "VBUS", "A9"),
             ("passive", 13.97, 5.08, 180, "VBUS", "B4"),
             ("passive", 13.97, 1.27, 180, "CC1", "A5"),
             ("passive", 13.97, -1.27, 180, "CC2", "B5"),
             ("passive", 13.97, -5.08, 180, "D+", "A6"),
             ("passive", 13.97, -7.62, 180, "D+", "B6"),
             ("passive", 13.97, -10.16, 180, "D-", "A7"),
             ("passive", 13.97, -12.7, 180, "D-", "B7"),
             ("no_connect", 13.97, -16.51, 180, "SBU1", "A8"),
             ("no_connect", 13.97, -19.05, 180, "SBU2", "B8"),
             ("passive", -13.97, -16.51, 0, "GND", "A1"),
             ("passive", -13.97, -19.05, 0, "GND", "B1"),
             ("passive", -13.97, -21.59, 0, "GND", "A12"),
             ("passive", -13.97, -24.13, 0, "GND", "B12"),
             ("passive", -13.97, -26.67, 0, "SHIELD", "S1")]
    s = lib_header("USB_C_16P", "J", "TYPE-C-31-M-12", hide_pin_names=False)
    s += '''      (symbol "USB_C_16P_0_1"
        (rectangle (start -11.43 15.24) (end 11.43 -29.21)
          (stroke (width 0.254) (type default)) (fill (type background)))
      )
      (symbol "USB_C_16P_1_1"
'''
    for (pt, x, yy, rot, pn, num) in upins:
        s += sym_pin(pt, x, yy, rot, pn, num) + "\n"
    s += "      )\n    )\n"
    L.append(s)
    # --- battery connector ---
    L.append(boxsym("Conn_Battery", "J", "JST-PH-2 LiPo", 10.16, [
        ("passive", 7.62, 2.54, 180, "BAT+", 1),
        ("passive", 7.62, -2.54, 180, "BAT-", 2)]))
    # --- SPDT slide switch ---
    s = lib_header("SW_SPDT_Slide", "SW", "MSK-12C02")
    s += '''      (symbol "SW_SPDT_Slide_0_1"
        (circle (center -2.032 0) (radius 0.508) (stroke (width 0) (type default)) (fill (type none)))
        (circle (center 2.032 1.27) (radius 0.508) (stroke (width 0) (type default)) (fill (type none)))
        (circle (center 2.032 -1.27) (radius 0.508) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy -1.524 0) (xy 1.524 1.016)) (stroke (width 0.254) (type default)) (fill (type none)))
      )
      (symbol "SW_SPDT_Slide_1_1"
'''
    s += sym_pin("passive", 5.08, 1.27, 180, "A", "1", length=2.54) + "\n"
    s += sym_pin("passive", -5.08, 0, 0, "C", "2", length=2.54) + "\n"
    s += sym_pin("passive", 5.08, -1.27, 180, "B", "3", length=2.54) + "\n"
    s += "      )\n    )\n"
    L.append(s)
    return "\n".join(L)

# ---- schematic symbol instance ---------------------------------------------
def sym_inst(lib, ref, val, x, y, rot, pin_nums, footprint="", props=None):
    rr = f" {rot}" if rot else ""
    pins = "\n".join(f'    (pin "{n}" (uuid "{NU("ipin", ref, n)}"))' for n in pin_nums)
    # extra BOM-relevant properties (MPN, Manufacturer, BOM Comments, ...)
    # -- hidden on the sheet, read by BOM tooling.
    extra = "".join(
        f'\n    (property "{k}" "{v}" (at {g(x)} {g(y)} 0) '
        f'(effects (font (size 1.27 1.27)) (hide yes)))'
        for k, v in (props or {}).items())
    return f'''  (symbol (lib_id "kbd:{lib}") (at {g(x)} {g(y)}{rr}) (unit 1)
    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (fields_autoplaced yes)
    (uuid "{U("sym", ref)}")
    (property "Reference" "{ref}" (at {g(x)} {g(y - 5.08)} 0) {FONT})
    (property "Value" "{val}" (at {g(x)} {g(y + 5.08)} 0) {FONT})
    (property "Footprint" "{footprint}" (at {g(x)} {g(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "~" (at {g(x)} {g(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Description" "" (at {g(x)} {g(y)} 0) (effects (font (size 1.27 1.27)) (hide yes))){extra}
{pins}
    (instances (project "{PROJ}" (path "/{ROOT_UUID}" (reference "{ref}") (unit 1))))
  )'''

def build_schematic():
    parts = []
    labels = []
    wires = []
    ncs = []
    texts = []
    # ---------------- matrix ----------------
    texts.append(sch_text("KEY MATRIX  5x12 (59 keys, COL2ROW diodes)", 25.4, 20.32, 3.81))
    swidx = {}
    for i, (r, c, u2) in enumerate(KEYS):
        swidx[(r, c)] = i + 1
        xo = 25.4 + c * 30.48
        yo = 30.48 + r * 12.7
        swref = f"SW{i+1}"
        dref = f"D{i+1}"
        labels.append(sch_glabel(f"COL{c}", xo, yo, 180))
        wires.append(sch_wire(xo, yo, xo + 2.54, yo))
        # The BOM line for each key position is the HOT-SWAP SOCKET (the
        # part actually soldered to the PCB), not the KS-33 switch that
        # plugs into it -- switches and keycaps are user-installed and
        # ordered separately (keyboard vendors, not DigiKey/LCSC).
        sock_note = ("Hot-swap socket (soldered, PCB assembly). The Gateron "
                     "KS-33 switch + keycap plug in and are ordered "
                     "separately -- keyboard vendors, not on DigiKey.")
        if u2:
            sock_note += " 2U key position: needs a 2U keycap + stabilizer."
        parts.append(sym_inst("SW_Push", swref, "KS-2P02B01-02",
                              xo + 5.08, yo, 180, ["1", "2"],
                              "kbd:SW_Gateron_KS33_HS",
                              props={"MPN": "KS-2P02B01-02",
                                     "Manufacturer": "Gateron",
                                     "BOM Comments": sock_note}))
        wires.append(sch_wire(xo + 7.62, yo, xo + 10.16, yo))
        parts.append(sym_inst("D_kbd", dref, "1N4148W", xo + 13.97, yo, 180,
                              ["1", "2"], "kbd:D_SOD-123_Back"))
        labels.append(sch_glabel(f"ROW{r}", xo + 17.78, yo, 0))
    # ---------------- MCU (RP2040 chip-down) ----------------
    mx, my = 127.0, 165.1
    texts.append(sch_text("MCU -- RP2040 (VERIFY pin numbers before fab, see file header)",
                          96.52, 100.33, 3.81))
    rp_pin_nums = [str(n) for (n, _l, _net) in RP2040_PINOUT] + [str(RP2040_THERMAL_PAD)]
    parts.append(sym_inst("RP2040", "U1", "RP2040", mx, my, 0, rp_pin_nums, "kbd:RP2040_QFN56"))
    left_half = RP2040_PINOUT[:28]
    right_half = RP2040_PINOUT[28:]
    # NOTE: KiCad symbol-library pin Y is authored Y-up, but the schematic
    # sheet is Y-down -- placing a symbol at rot=0 negates each pin's local Y
    # to get its absolute position. Label position must be (center_x + local_x,
    # center_y - local_y) to land exactly on the pin. Verified against the
    # untouched, working MCP73831 wiring elsewhere in this file.
    local_y0 = 2.54 * (len(left_half) - 1) / 2
    for i, (num, label, netname) in enumerate(left_half):
        local_y = local_y0 - i * 2.54
        py = my - local_y
        if netname is None:
            ncs.append(sch_nc(mx - 15.24, py))
        else:
            labels.append(sch_glabel(netname, mx - 15.24, py, 180))
    local_y0 = 2.54 * (len(right_half) - 1) / 2
    for i, (num, label, netname) in enumerate(right_half):
        local_y = local_y0 - i * 2.54
        py = my - local_y
        if netname is None:
            ncs.append(sch_nc(mx + 15.24, py))
        else:
            labels.append(sch_glabel(netname, mx + 15.24, py, 0))
    epad_local_y = -2.54 * (len(left_half) / 2) - 2.54
    labels.append(sch_glabel("GND", mx, my - epad_local_y, 90))

    # helper for 2-pin horizontal parts with labels at both ends
    def two_pin(ref, lib, val, x, y, n_left, n_right, fp, rot=0, pin_x=3.81):
        parts.append(sym_inst(lib, ref, val, x, y, rot, ["1", "2"], fp))
        if rot == 0:
            lx, rx = x - pin_x, x + pin_x
        else:  # 180
            lx, rx = x - pin_x, x + pin_x  # symmetric pins
        labels.append(sch_glabel(n_left, lx, y, 180))
        labels.append(sch_glabel(n_right, rx, y, 0))

    R0603 = "kbd:RC_0603"
    C0603 = "kbd:RC_0603"

    # ---- RP2040 minimum system: core supply, crystal, QSPI flash ----
    # All coordinates below are multiples of 1.27mm (schematic grid, enforced
    # by g()/sch_text/sch_glabel -- off-grid values raise an assertion).
    texts.append(sch_text("RP2040 minimum system (core regulator, 12MHz xtal, QSPI flash)",
                          96.52, 63.5, 3.0))
    # Core supply per the real RP2040 datasheet's "Core Supply Regulator"
    # chapter (Fig. 20 application circuit): the on-chip regulator is a
    # simple linear/LDO type (VREG_VIN -> VREG_VOUT -> DVDD), NOT a buck
    # converter -- no external inductor. VREG_VIN shares the +3V3 (IOVDD)
    # rail; VREG_VOUT and both DVDD pins are one net, each needing local
    # decoupling (1uF at VREG_VOUT, 100nF at each DVDD pin per the datasheet).
    two_pin("C9", "C_kbd", "1u", 96.52, 69.85, "DVDD", "GND", C0603)      # at VREG_VOUT
    two_pin("C32", "C_kbd", "100n", 109.22, 69.85, "DVDD", "GND", C0603)  # at DVDD pin 23
    two_pin("C33", "C_kbd", "100n", 96.52, 76.2, "DVDD", "GND", C0603)    # at DVDD pin 50
    two_pin("C34", "C_kbd", "1u", 109.22, 76.2, "VREG_VIN", "GND", C0603)
    two_pin("C10", "C_kbd", "1u", 96.52, 82.55, "+3V3", "GND", C0603)   # IOVDD bulk
    two_pin("C11", "C_kbd", "100n", 109.22, 82.55, "+3V3", "GND", C0603)  # IOVDD decoupling
    two_pin("R9", "R_kbd", "1k", 96.52, 88.9, "RUN", "+3V3", R0603)     # RUN pull-up
    two_pin("C12", "C_kbd", "100n", 109.22, 88.9, "RUN", "GND", C0603)   # RUN debounce
    parts.append(sym_inst("XTAL", "Y1", "12MHz", 96.52, 95.25, 0, ["1", "2"], "kbd:XTAL_3225"))
    labels.append(sch_glabel("XIN", 92.71, 95.25, 180))
    labels.append(sch_glabel("XOUT", 100.33, 95.25, 0))
    two_pin("C13", "C_kbd", "18p", 92.71, 101.6, "XIN", "GND", C0603)
    two_pin("C14", "C_kbd", "18p", 102.87, 101.6, "XOUT", "GND", C0603)
    parts.append(sym_inst("FLASH_QSPI", "U5", "W25Q16JVUXIQ", 96.52, 107.95, 0,
                          ["1","2","3","4","5","6","7","8"], "kbd:FLASH_USON8"))
    # y = center_y - local_pin_y (Y-flip, see U1 comment above)
    labels.append(sch_glabel("QSPI_SS", 86.36, 104.14, 180))
    labels.append(sch_glabel("QSPI_SD1", 86.36, 106.68, 180))
    labels.append(sch_glabel("QSPI_SD2", 86.36, 109.22, 180))
    labels.append(sch_glabel("GND", 86.36, 111.76, 180))
    labels.append(sch_glabel("QSPI_SD0", 106.68, 111.76, 0))
    labels.append(sch_glabel("QSPI_SCLK", 106.68, 109.22, 0))
    labels.append(sch_glabel("QSPI_SD3", 106.68, 106.68, 0))
    labels.append(sch_glabel("+3V3", 106.68, 104.14, 0))
    two_pin("C15", "C_kbd", "100n", 96.52, 114.3, "+3V3", "GND", "kbd:RC_0402")

    # ---- CYW43439 wireless (BLE-only) -- datasheet-verified net plan ----
    # Crystal freq, ball map, BT UART interface and power topology are from
    # the real Infineon/Cypress CYW43439 datasheet (002-30348 Rev *D).
    # Remaining VERIFY items: RF antenna-matching component values (the
    # datasheet itself says "consult reference schematics" -- genuinely
    # vendor/antenna-specific, not something a datasheet read resolves) and
    # the crystal's series-resistor value (datasheet: "determined by crystal
    # drive level, see reference schematics").
    texts.append(sch_text("Wireless (CYW43439, BLE-only) -- crystal/pinout/power topology "
                          "verified against datasheet 002-30348 Rev *D; RF matching values "
                          "still VERIFY (vendor/antenna-specific)", 96.52, 114.3, 2.5))
    parts.append(sym_inst("CYW43439_WLBGA63", "U6", "CYW43439", 96.52, 152.4, 0,
                          ["A2","A1","C3","B2","E6","B1","C1","G6","M4","M5","K1","F1","F2",
                           "A6","C7","M2","M3","C6","D6","E7","M1","H1","F6","B7","F7","G1","D4"],
                          "kbd:CYW43439_WLBGA63"))
    # label x = center_x -/+ 12.7 (matches pin x); y = center_y - local_pin_y (Y-flip, see U1 comment above)
    labels.append(sch_glabel("BT_UART_TXD", 83.82, 137.16, 180))
    labels.append(sch_glabel("BT_UART_RXD", 83.82, 139.7, 180))
    labels.append(sch_glabel("BT_UART_RTS_N", 83.82, 142.24, 180))
    labels.append(sch_glabel("BT_UART_CTS_N", 83.82, 144.78, 180))
    labels.append(sch_glabel("BT_REG_ON", 83.82, 147.32, 180))
    labels.append(sch_glabel("BT_DEV_WAKE", 83.82, 149.86, 180))
    labels.append(sch_glabel("BT_HOST_WAKE", 83.82, 152.4, 180))
    labels.append(sch_glabel("GND", 83.82, 154.94, 180))     # WL_REG_ON tied low: WLAN unused
    labels.append(sch_glabel("CYW_XTAL_XOP", 83.82, 157.48, 180))
    labels.append(sch_glabel("CYW_XTAL_XON", 83.82, 160.02, 180))
    labels.append(sch_glabel("WLRF_ANT", 83.82, 162.56, 180))
    labels.append(sch_glabel("CYW_BT_VCO_VDD", 83.82, 165.1, 180))
    labels.append(sch_glabel("CYW_BTFM_PLL_VDD", 83.82, 167.64, 180))
    labels.append(sch_glabel("CYW_SR_VLX", 109.22, 137.16, 0))
    labels.append(sch_glabel("CYW_VDD1P5", 109.22, 139.7, 0))
    labels.append(sch_glabel("CYW_VDD1P5", 109.22, 142.24, 0))   # WLRF_VDD_1P35, same node (Fig.3)
    labels.append(sch_glabel("CYW_XTAL_VDD1P2", 109.22, 144.78, 0))
    labels.append(sch_glabel("CYW_VOUT_CLDO", 109.22, 147.32, 0))
    labels.append(sch_glabel("CYW_VOUT_LNLDO", 109.22, 149.86, 0))
    labels.append(sch_glabel("CYW_VOUT_3P3", 109.22, 152.4, 0))
    labels.append(sch_glabel("CYW_PA_VDD", 109.22, 154.94, 0))
    labels.append(sch_glabel("CYW_PA_VDD", 109.22, 157.48, 0))   # BT_PAVDD, same node (Fig.4)
    labels.append(sch_glabel("+3V3", 109.22, 160.02, 0))         # WCC_VDDIO -- must match host I/O voltage
    labels.append(sch_glabel("VSYS", 109.22, 162.56, 0))         # SR_VDDBAT5V
    labels.append(sch_glabel("VSYS", 109.22, 165.1, 0))          # LDO_VDDBAT5V
    labels.append(sch_glabel("CYW_BT_IF_VDD", 109.22, 167.64, 0))
    labels.append(sch_glabel("GND", 96.52, 172.72, 90))

    # ---- internal-rail decoupling (values per datasheet Fig.3/Fig.4 where
    # given; VERIFY where marked -- generic decoupling default, not printed
    # in the datasheet for that specific ball) ----
    two_pin("C20", "C_kbd", "4.7u", 127.0, 137.16, "CYW_VDD1P5", "GND", C0603)
    two_pin("C21", "C_kbd", "100n (VERIFY)", 127.0, 139.7, "CYW_XTAL_VDD1P2", "GND", C0603)
    two_pin("C22", "C_kbd", "2.2u", 127.0, 142.24, "CYW_VOUT_CLDO", "GND", C0603)
    two_pin("C23", "C_kbd", "2.2u (VERIFY)", 127.0, 144.78, "CYW_VOUT_LNLDO", "GND", C0603)
    two_pin("C24", "C_kbd", "4.7u", 127.0, 147.32, "CYW_VOUT_3P3", "GND", C0603)
    two_pin("C25", "C_kbd", "1u", 127.0, 149.86, "CYW_PA_VDD", "GND", C0603)
    two_pin("C26", "C_kbd", "1u", 127.0, 152.4, "CYW_PA_VDD", "GND", C0603)
    two_pin("C27", "C_kbd", "100n (VERIFY)", 127.0, 154.94, "CYW_BT_VCO_VDD", "GND", C0603)
    two_pin("C28", "C_kbd", "100n (VERIFY)", 127.0, 157.48, "CYW_BTFM_PLL_VDD", "GND", C0603)
    two_pin("C29", "C_kbd", "100n (VERIFY)", 127.0, 160.02, "CYW_BT_IF_VDD", "GND", C0603)
    two_pin("L3", "R_kbd", "2.2uH", 127.0, 162.56, "CYW_SR_VLX", "CYW_VDD1P5", R0603)  # VERIFY: inductor symbol reuse (R_kbd shape, not a real inductor symbol)
    two_pin("R12", "R_kbd", "22", 127.0, 165.1, "CYW_VOUT_3P3", "CYW_PA_VDD", R0603)

    # ---- crystal: 37.4MHz per datasheet sec. 3.1 (default freq ref) ----
    parts.append(sym_inst("XTAL", "Y2", "37.4MHz", 96.52, 175.26, 0, ["1", "2"], "kbd:XTAL_3225"))
    labels.append(sch_glabel("CYW_XTAL_XOP", 92.71, 175.26, 180))
    labels.append(sch_glabel("CYW_XTAL_XON", 100.33, 175.26, 0))
    two_pin("C30", "C_kbd", "27p", 92.71, 181.61, "CYW_XTAL_XOP", "GND", C0603)
    two_pin("C31", "C_kbd", "27p", 102.87, 181.61, "CYW_XTAL_XON_J", "GND", C0603)
    two_pin("R13", "R_kbd", "0 (ref: Pico W)", 100.33, 187.96,
            "CYW_XTAL_XON", "CYW_XTAL_XON_J", R0603)

    # antenna matching pi-network -- values now grounded in Raspberry Pi's
    # own public Pico W hardware design files (RPi-PicoW-PUBLIC-20220607.zip,
    # RPI-PICOW-R2.DSN), which uses the same CYW43439/BCM43438 die and a
    # 37.4MHz crystal (confirms this file's Y2). Raspberry Pi's own BOM
    # there shows a 4.7nH 0603 chip inductor plus a small C0G chip cap
    # selected from a documented "BOM Variants" family spanning
    # 0.2/0.3/0.36/0.5/0.8/1.3/2.0pF (Murata GJM1555C1H series) -- i.e. even
    # Raspberry Pi's own production board doesn't use one fixed universal
    # value here; the exact pF is chosen per their specific PCB
    # trace/antenna during RF characterization. But that reference pairs
    # the CYW43439 with Abracon/Proant's own proprietary PCB-trace antenna
    # (undocumented geometry) -- this design instead terminates in a real,
    # purchasable chip antenna (Johanson 2450AT18B100E, see
    # fp_antenna_johanson), so L2/C17 below use JOHANSON'S OWN published
    # reference matching values for that exact antenna (datasheet Ver. 4.0,
    # "Mounting Considerations": 2.7nH series inductor + 1.2pF shunt cap,
    # against a 50-ohm source) as the better-grounded starting point. C18
    # stays DNP as a second tuning element (their reference circuit uses a
    # 2nd series inductor rather than a 2nd shunt cap -- topology, not just
    # values, will need real RF tuning on this board's own layout either way).
    two_pin("L2", "R_kbd", "2.7nH (ref: Johanson)", 96.52, 194.31, "WLRF_ANT", "WLRF_ANT_MID", "kbd:RC_0201")
    two_pin("C17", "C_kbd", "1.2p (ref: Johanson)", 90.17, 196.85, "WLRF_ANT", "GND", "kbd:RC_0402")
    two_pin("C18", "C_kbd", "DNP (VERIFY, tune)", 102.87, 196.85, "WLRF_ANT_MID", "GND", "kbd:RC_0402")
    labels.append(sch_glabel("WLRF_ANT_MID", 96.52, 200.66, 270))
    parts.append(sym_inst("ANT_JOHANSON", "ANT1", "2450AT18B100E", 96.52, 205.74, 0,
                          ["1", "2"], "kbd:ANT_JOHANSON_2450AT18B100"))
    labels.append(sch_glabel("WLRF_ANT_MID", 90.17, 205.74, 180))
    ncs.append(sch_nc(102.87, 205.74))

    # ---- per-key RGB chain (59x SK6812MINI-E) ----
    texts.append(sch_text("Per-key RGB -- SK6812MINI-E x59, serpentine chain "
                          "(must match Sources/smk/RGBLighting.swift ledChainIndex)",
                          25.4, 45.72, 3.0))
    parts.append(sym_inst("LVL_SHIFT_BUF", "U7", "SN74AHCT1G125DBVR", 60.96, 54.61, 0,
                          ["1","2","3","4","5"], "kbd:SOT-23-5"))
    # y = center_y - local_pin_y (Y-flip, see U1 comment above)
    labels.append(sch_glabel("GND", 50.8, 52.07, 180))     # OE# tied low = enabled
    labels.append(sch_glabel("RGB_GPIO", 50.8, 54.61, 180))
    labels.append(sch_glabel("GND", 50.8, 57.15, 180))
    labels.append(sch_glabel("LEDD0", 71.12, 54.61, 0))
    labels.append(sch_glabel("VSYS", 71.12, 52.07, 0))      # level shifter VCC from VSYS (not the 3.3V rail -- see RGB power note below)
    two_pin("R10", "R_kbd", "330", 60.96, 60.96, "LEDD0", "LEDD0_R", R0603)
    two_pin("C19", "C_kbd", "10u", 71.12, 60.96, "VSYS", "GND", C0603)
    texts.append(sch_text("RGB power budget (calculated from the SK6812MINI-E datasheet, "
                          "12mA/channel x 3 x 59 LEDs = 2.12A max at full white): fed from "
                          "VSYS, NOT the 3.3V LDO (AP2112K-3.3 isn't remotely rated for this). "
                          "D60 (B5819W, ~1A avg rating) IS in this path when USB-powered and "
                          "WOULD be exceeded by 2.12A -- firmware must cap brightness/"
                          "concurrent-on count well below full-white-all-keys regardless of "
                          "power source. Also VERIFY: SK6812MINI-E's own datasheet specs VDD "
                          "3.7-5.5V, and VSYS (Li-ion battery) can sag below 3.7V well within "
                          "normal discharge range -- LEDs may misbehave on a low battery even "
                          "with brightness capped. Level shifter keeps DIN threshold margin "
                          "safe across the VSYS voltage range (separate from the VDD-minimum "
                          "concern above).", 25.4, 38.1, 1.6))
    for i, (r, c) in enumerate(LED_CHAIN):
        ref = f"RGB{i+1}"
        din_net = "LEDD0_R" if i == 0 else f"LEDD{i}"
        dout_net = f"LEDD{i+1}"
        lx = 25.4 + c * 30.48
        ly = 30.48 + r * 12.7 + 3.81  # offset south of key center (3x1.27 grid step)
                                      # -- VERIFY against Gateron KS-33 mechanical
                                      # drawing for the actual LED window position
        parts.append(sym_inst("SK6812MINI", ref, "SK6812MINI-E", lx, ly, 0,
                              ["1", "2", "3", "4"], "kbd:SK6812MINI_E"))
        # x = lx -/+ 8.89 (matches pin x); y = ly - local_pin_y (Y-flip, see U1 comment above)
        labels.append(sch_glabel(din_net, lx - 8.89, ly - 2.54, 180))
        labels.append(sch_glabel("GND", lx - 8.89, ly + 2.54, 180))
        labels.append(sch_glabel(dout_net, lx + 8.89, ly - 2.54, 0))
        labels.append(sch_glabel("VSYS", lx + 8.89, ly + 2.54, 0))
        # Local decoupling per LED, not just one bulk cap at the chain's
        # start (C19) -- the SK6812MINI-E datasheet's own typical
        # application circuit shows a cap at every LED ("even the
        # capacitance between beads is essential"); with 59 in a chain and
        # trace inductance between them, one cap far upstream wouldn't hold
        # up the local rail during each LED's own fast PWM current step.
        two_pin(f"C{100+i}", "C_kbd", "100n", lx, ly + 6.35, "VSYS", "GND", C0603)
    ncs.append(sch_nc(25.4 + LED_CHAIN[-1][1] * 30.48 + 8.89, 30.48 + LED_CHAIN[-1][0] * 12.7 + 3.81 - 2.54))

    # ---------------- USB ----------------
    texts.append(sch_text("USB-C  (charge + native USB)", 219.71, 105.41, 3.81))
    ux, uy = 241.3, 127.0
    parts.append(sym_inst("USB_C_16P", "J1", "TYPE-C-31-M-12", ux, uy, 0,
                          ["A1","A4","A5","A6","A7","A8","A9","A12",
                           "B1","B4","B5","B6","B7","B8","B9","B12","S1"],
                          "kbd:USB_C_Receptacle_HRO_TYPE-C-31-M-12"))
    for py, nm in [(-12.7,"VBUS"),(-10.16,"VBUS"),(-7.62,"VBUS"),(-5.08,"VBUS"),
                   (-1.27,"CC1"),(1.27,"CC2"),(5.08,"USB_DP"),(7.62,"USB_DP"),
                   (10.16,"USB_DM"),(12.7,"USB_DM")]:
        labels.append(sch_glabel(nm, ux + 13.97, uy + py, 0))
    ncs.append(sch_nc(ux + 13.97, uy + 16.51))
    ncs.append(sch_nc(ux + 13.97, uy + 19.05))
    for py in (16.51, 19.05, 21.59, 24.13, 26.67):
        labels.append(sch_glabel("GND", ux - 13.97, uy + py, 180))
    two_pin("R1", "R_kbd", "5.1k", 273.05, 116.84, "CC1", "GND", R0603)
    two_pin("R2", "R_kbd", "5.1k", 273.05, 127.0, "CC2", "GND", R0603)
    # ESD
    ex, ey = 241.3, 171.45
    parts.append(sym_inst("USBLC6-2SC6", "U4", "USBLC6-2SC6", ex, ey, 0,
                          ["1","2","3","4","5","6"], "kbd:SOT-23-6"))
    labels.append(sch_glabel("USB_DM", ex - 8.89, ey - 2.54, 180))
    labels.append(sch_glabel("GND",    ex - 8.89, ey, 180))
    labels.append(sch_glabel("USB_DP", ex - 8.89, ey + 2.54, 180))
    labels.append(sch_glabel("USB_DP", ex + 8.89, ey - 2.54, 0))
    labels.append(sch_glabel("VBUS",   ex + 8.89, ey, 0))
    labels.append(sch_glabel("USB_DM", ex + 8.89, ey + 2.54, 0))
    # ---------------- charger ----------------
    texts.append(sch_text("Li-ion charger 500mA", 287.02, 105.41, 3.81))
    cx, cy = 298.45, 116.84
    parts.append(sym_inst("MCP73831", "U2", "MCP73831-2ACI/OT", cx, cy, 0,
                          ["1","2","3","4","5"], "kbd:SOT-23-5"))
    labels.append(sch_glabel("VBUS", cx - 10.16, cy - 2.54, 180))
    labels.append(sch_glabel("GND",  cx - 10.16, cy + 2.54, 180))
    labels.append(sch_glabel("BAT+", cx + 10.16, cy - 2.54, 0))
    labels.append(sch_glabel("STAT", cx + 10.16, cy, 0))
    labels.append(sch_glabel("PROG", cx + 10.16, cy + 2.54, 0))
    two_pin("R3", "R_kbd", "2.0k", 298.45, 133.35, "PROG", "GND", R0603)
    two_pin("C1", "C_kbd", "4.7u", 298.45, 146.05, "VBUS", "GND", C0603)
    two_pin("C2", "C_kbd", "4.7u", 298.45, 158.75, "BAT+", "GND", C0603)
    two_pin("R4", "R_kbd", "1k", 320.04, 133.35, "VBUS", "LED_A", R0603)
    two_pin("LED1", "LED_kbd", "CHG", 320.04, 146.05, "STAT", "LED_A",
            "kbd:LED_0603")
    parts.append(sym_inst("Conn_Battery", "J2", "JST-SH-2 SM02B", 320.04, 116.84, 0,
                          ["1", "2"], "kbd:JST_SH_SM02B_2pin_Back"))
    labels.append(sch_glabel("BAT+", 327.66, 114.3, 0))
    labels.append(sch_glabel("GND", 327.66, 119.38, 0))
    # ---------------- power path / LDO ----------------
    texts.append(sch_text("Power path + 3.3V LDO + ON/OFF", 340.36, 105.41, 3.81))
    two_pin("D60", "D_Schottky_kbd", "B5819W", 353.06, 116.84, "VSYS", "VBUS",
            "kbd:D_SOD-123_Back")  # K=VSYS  A=VBUS
    qx, qy = 353.06, 133.35
    parts.append(sym_inst("Q_PMOS_GSD", "Q1", "DMG3415U", qx, qy, 0,
                          ["1", "2", "3"], "kbd:SOT-23"))
    labels.append(sch_glabel("VBUS", qx - 7.62, qy, 180))
    labels.append(sch_glabel("BAT+", qx, qy - 5.08, 90))
    labels.append(sch_glabel("VSYS", qx, qy + 5.08, 270))
    lx, ly = 353.06, 158.75
    parts.append(sym_inst("AP2112K-3.3", "U3", "AP2112K-3.3", lx, ly, 0,
                          ["1","2","3","4","5"], "kbd:SOT-23-5"))
    labels.append(sch_glabel("VSYS",   lx - 10.16, ly - 2.54, 180))
    labels.append(sch_glabel("EN_LDO", lx - 10.16, ly, 180))
    labels.append(sch_glabel("GND",    lx - 10.16, ly + 2.54, 180))
    labels.append(sch_glabel("+3V3",   lx + 10.16, ly - 2.54, 0))
    ncs.append(sch_nc(lx + 10.16, ly + 2.54))
    # slide switch
    sx, sy = 298.45, 176.53
    parts.append(sym_inst("SW_SPDT_Slide", "SW62", "PWR MSK-12C02", sx, sy, 0,
                          ["1", "2", "3"], "kbd:SW_Slide_MSK12C02"))
    labels.append(sch_glabel("EN_LDO", sx - 5.08, sy, 180))
    labels.append(sch_glabel("VSYS", sx + 5.08, sy - 1.27, 0))
    labels.append(sch_glabel("GND", sx + 5.08, sy + 1.27, 0))
    two_pin("R5", "R_kbd", "100k", 298.45, 189.23, "EN_LDO", "GND", R0603)
    two_pin("C3", "C_kbd", "1u", 353.06, 174.0 - 0.0, "VSYS", "GND", C0603) if False else None
    two_pin("C3", "C_kbd", "1u", 353.06, 173.99, "VSYS", "GND", C0603)
    two_pin("C4", "C_kbd", "10u", 353.06, 186.69, "+3V3", "GND", C0603)
    # ---------------- battery sense / EN / boot ----------------
    texts.append(sch_text("VBAT sense + RESET + BOOTSEL", 391.16, 105.41, 3.81))
    two_pin("R6", "R_kbd", "1M", 402.59, 116.84, "BAT+", "VBAT_SENSE", R0603)
    two_pin("R7", "R_kbd", "1M", 402.59, 129.54, "VBAT_SENSE", "GND", R0603)
    two_pin("C5", "C_kbd", "100n", 402.59, 142.24, "VBAT_SENSE", "GND", C0603)
    two_pin("C7", "C_kbd", "10u", 402.59, 180.34, "+3V3", "GND", C0603)
    two_pin("C8", "C_kbd", "100n", 402.59, 193.04, "+3V3", "GND", C0603)
    parts.append(sym_inst("SW_Push", "SW60", "RESET", 172.72, 203.2, 0, ["1","2"],
                          "kbd:SW_PUSH_6mm_THT"))
    labels.append(sch_glabel("RUN", 170.18, 203.2, 180))
    labels.append(sch_glabel("GND", 175.26, 203.2, 0))
    # BOOTSEL: VERIFY -- on real Pico, this button shorts QSPI_SS to GND
    # through a small series resistor (protects against contention once
    # QSPI_SS is driven as an output post-boot). Reproduced here; confirm
    # against the RP2040 datasheet boot-select section before fab.
    parts.append(sym_inst("SW_Push", "SW61", "BOOTSEL (VERIFY)", 198.12, 203.2, 0, ["1","2"],
                          "kbd:SW_PUSH_6mm_THT"))
    labels.append(sch_glabel("BOOTSEL", 195.58, 203.2, 180))
    labels.append(sch_glabel("GND", 200.66, 203.2, 0))
    two_pin("R11", "R_kbd", "330", 198.12, 210.82, "BOOTSEL", "QSPI_SS", R0603)
    texts.append(sch_text("GPIO map (VERIFY pin numbers, see file header):  ROW0-4 = GPIO0-4   "
                          "COL0-11 = GPIO5-16   RGB_GPIO = GPIO17   VBAT_SENSE = GPIO26/ADC0   "
                          "BT UART/ctrl (GPIO18-23, 28) = CYW43439 BLE link (see wireless section)",
                          25.4, 95.25, 2.0))
    texts.append(sch_text("Charging works with power switch OFF (charger connects before switch).  "
                          "BOOTSEL+RESET = USB mass-storage bootloader mode (VERIFY).",
                          25.4, 100.33, 2.0))

    body = "\n".join(texts + [p for p in parts if p] + wires + labels + ncs)
    return f'''(kicad_sch (version 20231120) (generator "eeschema") (generator_version "8.0")
  (uuid "{ROOT_UUID}")
  (paper "A2")
  (title_block
    (title "Gateron LP 5x12 wireless keyboard -- RP2040 variant")
    (company "")
    (rev "A")
    (comment 1 "RP2040+CYW43439 chip-down (VERIFY before fab), per-key RGB, Li-ion, hot-swap Gateron KS-33")
  )
  (lib_symbols
{build_lib_symbols()}  )
{body}
  (sheet_instances (path "/" (page "1")))
)
'''

# ============================================================ PCB ==========
BOARD = dict(x1=37.5, y1=22.0, x2=272.0, y2=138.5)

def build_pcb():
    fps = []
    # ---- keys + diodes ----
    for i, (r, c, u2) in enumerate(KEYS):
        x, y = key_pos(r, c, u2)
        n_sw = f"N_R{r}C{c}"
        fps.append(fp_gateron(f"SW{i+1}", x, y, n_sw, f"COL{c}",
                              U("sym", f"SW{i+1}"), is2u=u2))
        fps.append(fp_diode(f"D{i+1}", x - 8.5, y + 1.0, 270,
                            f"ROW{r}", n_sw, U("sym", f"D{i+1}")))
    # ---- MCU (RP2040 chip-down) ----
    # Kept at the ESP32's old position -- preserves the matrix-fanout
    # geometry (front layer free under the matrix, MCU facing the keys)
    # that the rest of this file's routing conventions assume.
    rp_net = {n: netname for (n, _label, netname) in RP2040_PINOUT}
    rp_net[RP2040_THERMAL_PAD] = "GND"
    fps.append(fp_rp2040("U1", 154.75, 31.0, U("sym", "U1"), rp_net))

    # RP2040 minimum system: core supply, crystal, decoupling -- placed in
    # the region above/right of U1 that opened up once the wireless section
    # moved to the (previously antenna-only) left edge. Generous spacing to
    # clear U1's and each other's courtyards (verified via analyze_pcb.py).
    # Core supply per the real RP2040 datasheet (linear/LDO on-chip
    # regulator, VREG_VIN -> VREG_VOUT -> DVDD -- no external inductor;
    # see the matching comment in build_schematic for the datasheet basis).
    fps.append(fp_0603("C9", "1u", 160.0, 24.5, 0, U("sym", "C9"), "DVDD", "GND"))
    fps.append(fp_0603("C32", "100n", 164.0, 24.5, 0, U("sym", "C32"), "DVDD", "GND"))
    # moved off the C9/C32/... row entirely (was 168.0, 24.5): that whole
    # row sits in a genuine pinch between SW61 (BOOTSEL)'s NW through-hole
    # pad and QSPI_SD1's own deterministic F-layer lane/elevator column
    # (y=23.75, x=170.0) -- the two obstacles' required clearance zones
    # overlap by design, leaving no legal x anywhere on that row (checked
    # the full band algebraically: SW61 needs center>=168.525, QSPI's
    # elevator needs center<=168.525 -- a single point, not a window).
    # Moved south instead, still reasonably close to U1's DVDD pins 45/50
    # (27.35) for decoupling, clear of Y1/C13/C14 and the row above.
    fps.append(fp_0603("C33", "100n", 168.0, 33.0, 0, U("sym", "C33"), "DVDD", "GND"))
    fps.append(fp_0603("C34", "1u", 172.0, 24.5, 0, U("sym", "C34"), "VREG_VIN", "GND"))
    fps.append(fp_0603("C10", "1u", 176.0, 24.5, 0, U("sym", "C10"), "+3V3", "GND"))
    fps.append(fp_0603("C11", "100n", 180.0, 24.5, 0, U("sym", "C11"), "+3V3", "GND"))
    fps.append(fp_crystal_smd("Y1", "12MHz", 164.0, 30.0, 0, U("sym", "Y1"), "XIN", "XOUT"))
    fps.append(fp_0603("C13", "18p", 161.5, 26.5, 0, U("sym", "C13"), "XIN", "GND"))
    fps.append(fp_0603("C14", "18p", 166.5, 26.5, 0, U("sym", "C14"), "XOUT", "GND"))
    # U5 was at (166.5, 35.0) -- SOUTH-EAST of U1 while the QSPI pins exit
    # NORTH. Every QSPI line had to wrap around U1's east side, and the
    # resulting lane/elevator system (QSPI_SD1's F lane at y=23.75 plus
    # the x=170-174 elevators) sealed the whole U1-north pocket: QSPI_SD2/
    # SCLK/SD3, XIN, VREG_VIN and USB_DM/DP were all unroutable behind it
    # (verified by probing the router's own A* masks). Moved directly WEST
    # of the QSPI pin bank -- the Pico reference design's arrangement.
    # At (149.8, 24.0) rot 0, the footprint's east column lands pins
    # 8/7/6/5 (VCC/SD3/SCLK/SD0) top-to-bottom at x=151.075, y=23.25/
    # 23.75/24.25/24.75 -- so SD3/SCLK/SD0's escape stubs (x 154.15/
    # 153.75/153.35) can run dead-straight west into their pads, and
    # SS/SD1/SD2 wrap around the west column (see route_kbd_rp2040.py's
    # QSPI section for the verified lane geometry).
    fps.append(fp_flash8("U5", 149.8, 24.0, 0, U("sym", "U5"),
                         {1: "QSPI_SS", 2: "QSPI_SD1", 3: "QSPI_SD2", 4: "GND",
                          5: "QSPI_SD0", 6: "QSPI_SCLK", 7: "QSPI_SD3", 8: "+3V3"}))
    # C15 follows U5 (it's U5's VCC decoupling): 0402 now, tucked into the
    # band above the QSPI stub tips, pad 1 (+3V3) 1.1mm from U5 pin 8.
    fps.append(fp_0402("C15", "100n", 152.7, 23.0, 0, U("sym", "C15"), "+3V3", "GND"))
    fps.append(fp_0603("R9", "1k", 184.0, 24.5, 0, U("sym", "R9"), "RUN", "+3V3"))
    fps.append(fp_0603("C12", "100n", 188.0, 24.5, 0, U("sym", "C12"), "RUN", "GND"))

    # RGB level shifter -- also relocated into the freed-up region, still
    # close to U1's RGB_GPIO exit (a left-side pin) via a short trace.
    fps.append(fp_sot23_5("U7", "SN74AHCT1G125DBVR", 176.0, 31.0, 0, U("sym", "U7"),
                          {1: "GND", 2: "RGB_GPIO", 3: "GND", 4: "LEDD0", 5: "VSYS"}))
    fps.append(fp_0603("R10", "330", 180.0, 31.0, 0, U("sym", "R10"), "LEDD0", "LEDD0_R"))
    fps.append(fp_0603("C19", "10u", 184.0, 31.0, 0, U("sym", "C19"), "VSYS", "GND"))

    # ---- CYW43439 wireless (BLE-only) -- real WLBGA-63 placement + keepout ----
    # Placed on the left edge, which is completely empty on the ESP32
    # board -- keeps the RF section away from the switching regulator and
    # digital fanout, with its own antenna keepout at the board's top edge.
    # Matching network (L2/C17/C18) sits OUTSIDE the keepout polygon
    # (keepout forbids footprints/pads); only the actual antenna element/
    # trace, not modeled here, would go inside it.
    fps.append(fp_cyw43439("U6", 45.0, 30.0, U("sym", "U6"), cyw_pinnet()))
    fps.append(fp_crystal_smd("Y2", "37.4MHz", 50.0, 30.0, 0, U("sym", "Y2"),
                              "CYW_XTAL_XOP", "CYW_XTAL_XON"))
    fps.append(fp_0603("C30", "27p", 54.0, 30.0, 0, U("sym", "C30"), "CYW_XTAL_XOP", "GND"))
    fps.append(fp_0603("C31", "27p", 58.0, 30.0, 0, U("sym", "C31"), "CYW_XTAL_XON_J", "GND"))
    fps.append(fp_0603("R13", "0 (ref: Pico W)", 62.0, 30.0, 0, U("sym", "R13"),
                       "CYW_XTAL_XON", "CYW_XTAL_XON_J"))
    # ROUTING NOTE for whoever routes U6-K1 -> L2 -> C17 -> C18 -> ANT1:
    # this trace needs to be ~0.40mm wide for 50-ohm on this board's 4-layer
    # stackup, referenced to In1.Cu just 0.2104mm below F.Cu (calculated via
    # Hammerstad-Jensen, not a guess -- see the file header "ANTENNA FEED
    # TRACE" section), with an unbroken GND pour on In1.Cu directly beneath
    # it outside the antenna_keepout zone. NOT the old 2-layer board's
    # ~3.0mm figure, and NOT the thin digital-signal trace width used
    # elsewhere on this board either.
    # rot 270 (was 90): puts pad 1 (WLRF_ANT, the U6 side) on the NORTH
    # side facing the chip and pad 2 (WLRF_ANT_MID, the antenna side) on
    # the SOUTH facing the feed run -- with the original orientation the
    # chip-side trace and the feed run had to cross each other to reach
    # their pads (see route_kbd_rp2040.py's U6 fanout section).
    fps.append(fp_0201("L2", "2.7nH (ref: Johanson)", 45.0, 34.5, 270, U("sym", "L2"), "WLRF_ANT", "WLRF_ANT_MID"))
    fps.append(fp_0402("C17", "1.2p (ref: Johanson)", 49.0, 34.5, 0, U("sym", "C17"), "WLRF_ANT", "GND"))
    fps.append(fp_0402("C18", "DNP (VERIFY, tune)", 53.0, 34.5, 0, U("sym", "C18"), "WLRF_ANT_MID", "GND"))
    # Real antenna, placed inside the antenna_keepout zone (below, y 22-26)
    # rather than leaving that zone empty -- see the file header and the
    # build_schematic comment above for why this specific part.
    fps.append(fp_antenna_johanson("ANT1", 45.0, 24.5, 0, U("sym", "ANT1"), "WLRF_ANT_MID"))
    fps.append(fp_0603("C20", "4.7u", 58.0, 34.5, 0, U("sym", "C20"), "CYW_VDD1P5", "GND"))
    fps.append(fp_0603("C21", "100n", 62.0, 34.5, 0, U("sym", "C21"), "CYW_XTAL_VDD1P2", "GND"))
    fps.append(fp_0603("C22", "2.2u", 66.0, 34.5, 0, U("sym", "C22"), "CYW_VOUT_CLDO", "GND"))
    fps.append(fp_0603("C23", "2.2u", 70.0, 34.5, 0, U("sym", "C23"), "CYW_VOUT_LNLDO", "GND"))
    fps.append(fp_0603("C24", "4.7u", 45.0, 38.5, 0, U("sym", "C24"), "CYW_VOUT_3P3", "GND"))
    fps.append(fp_0603("C25", "1u", 49.0, 38.5, 0, U("sym", "C25"), "CYW_PA_VDD", "GND"))
    fps.append(fp_0603("C26", "1u", 53.0, 38.5, 0, U("sym", "C26"), "CYW_PA_VDD", "GND"))
    fps.append(fp_0603("C27", "100n", 57.0, 38.5, 0, U("sym", "C27"), "CYW_BT_VCO_VDD", "GND"))
    fps.append(fp_0603("C28", "100n", 61.0, 38.5, 0, U("sym", "C28"), "CYW_BTFM_PLL_VDD", "GND"))
    fps.append(fp_0603("C29", "100n", 65.0, 38.5, 0, U("sym", "C29"), "CYW_BT_IF_VDD", "GND"))
    fps.append(fp_0603("L3", "2.2uH", 69.0, 38.5, 0, U("sym", "L3"), "CYW_SR_VLX", "CYW_VDD1P5"))
    fps.append(fp_0603("R12", "22", 73.0, 38.5, 0, U("sym", "R12"), "CYW_VOUT_3P3", "CYW_PA_VDD"))

    # ---- per-key RGB chain (59x SK6812MINI-E) ----
    # Placed NORTH of each key center (negative Y), per the switch
    # manufacturer's own "PCB Layout" mechanical drawing: the light-pipe
    # window sits on the OPPOSITE side of the stem from the two leg-
    # mounting NPTH holes, not the same side. The drawing gives the window
    # as a 6.40 x 0.55mm slot, centered on X=0, spanning 5.75-6.30mm from
    # switch center on the side away from the legs -- confirmed against
    # this footprint's own real hole positions (local (-4.4,4.7) and
    # (2.6,5.75), both south/+Y), which match the drawing's own dimensions
    # for those same two holes (4.70, 5.75, 2.60, 4.40) exactly. Window
    # center = -(5.75+6.30)/2 = -6.025.
    #
    # Earlier revisions of this fix (see git history) placed the LED SOUTH
    # of center instead -- at PITCH/2 (9.525mm, illuminated nothing, it
    # was the midpoint of the gap to the next row) and then at 5.9mm/5.4mm
    # (under the switch, but on the SAME side as the leg holes, which is
    # why the LED's own DIN pin kept landing inside a hole's keepout no
    # matter how it was routed -- that side is simply the wrong side).
    # This position is on the empty north side of the switch, clear of the
    # holes/pads by construction rather than by a tuned offset.
    LED_OFFSET_Y = -6.025
    for i, (r, c) in enumerate(LED_CHAIN):
        x, y = key_xy(r, c)
        ly = y + LED_OFFSET_Y
        din_net = "LEDD0_R" if i == 0 else f"LEDD{i}"
        dout_net = f"LEDD{i + 1}"
        # Pad numbering is the real KiCad standard footprint's own physical
        # layout (1=GND, 2=DOUT, 3=VDD, 4=DIN) -- see fp_sk6812mini.
        fps.append(fp_sk6812mini(f"RGB{i+1}", x, ly, 0, U("sym", f"RGB{i+1}"),
                                 {1: "GND", 2: dout_net, 3: "VSYS", 4: din_net}))
        # Local decoupling cap per LED (datasheet's own recommendation --
        # see build_schematic comment). Was offset +4mm in X at the LED's
        # own Y -- with the LED now sitting inside the switch's own
        # courtyard (south-facing fix above), that line ran straight
        # through the switch's own leg-mounting hole (a real NPTH,
        # unrelated to any net, at switch-local (2.6, 5.75)). A pure
        # +2mm-in-Y offset (tried next, straight south of the LED) cleared
        # that leg hole but sat inside the LED's OWN light-transmission
        # cutout (added later, after the reverse-mount LED redesign, and
        # never re-checked against this cap's position): the cutout's
        # radius (~2.23mm) needs ~2.83mm total clearance for a via/pad,
        # and +2mm falls well inside that. Straight south has no gap at
        # all between this cutout and the next row's own switch leg hole
        # (found by direct computation: the two required-clearance zones
        # butt up against each other with ~0mm to spare) -- so the offset
        # needs an X component too, not just more Y. -1.8mm X / +3.1mm Y
        # (found via grid search against the real accumulated board
        # items, checking BOTH of this 0402's own pads -- its footprint
        # is 0.97mm pad-to-pad, so a fix verified against only one pad
        # left the other one still inside a hole's keepout) clears both
        # holes, on both pads, with real margin.
        # Y offset then tightened 3.1 -> 3.0: at +3.1 the GND pad's nearest
        # corner sat 2.807mm from the switch's 5.2mm center-stem NPTH
        # (2.6mm hole radius) = 0.207mm hole-to-copper -- legal under the
        # old 0.2mm search rule but below drc_check.py's 0.25mm HOLE_MIN.
        # At +3.0 that corner distance is 2.900mm = 0.30mm clearance, and
        # the LED light-transmission cutout on the other side still has
        # >0.6mm to spare (its required-clearance zone starts ~2.83mm from
        # the LED center; this pad corner is ~2.88mm away).
        # Side moved F -> B: the vendor KS-33 STEP model's bottom housing
        # is FLUSH at z=0 across this spot (no molded recess -- checked the
        # model's own point cloud; the only relief is elsewhere, at z=0.5),
        # so a 0.35mm-tall 0402 on F.Cu here would keep the switch from
        # seating flat -- on all 59 keys. On B.Cu the same XY keeps every
        # hole clearance identical by symmetry, sits on the same layer as
        # the reverse-mount LED pads it decouples (no via needed in its
        # local loop), and physically shares the back side with the
        # 3.05mm-tall hot-swap socket, which dwarfs it.
        fps.append(fp_0402(f"C{100+i}", "100n", x - 1.8, ly + 3.0, 0, U("sym", f"C{100+i}"), "VSYS", "GND", side="B"))
    # ---- USB ----
    usb_net = {"A1": "GND", "B12": "GND", "A12": "GND", "B1": "GND", "S1": "GND",
               "A4": "VBUS", "B9": "VBUS", "A9": "VBUS", "B4": "VBUS",
               "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP",
               "A7": "USB_DM", "B7": "USB_DM", "A8": None, "B8": None}
    fps.append(fp_usbc("J1", 262.0, 25.6, 180, U("sym", "J1"), usb_net))
    # ---- power parts ----
    fps.append(fp_sot23_5("U2", "MCP73831", 216.0, 31.0, 0, U("sym", "U2"),
                          {1: "STAT", 2: "GND", 3: "BAT+", 4: "VBUS", 5: "PROG"}))
    fps.append(fp_sot23_5("U3", "AP2112K-3.3", 122.0, 33.5, 0, U("sym", "U3"),
                          {1: "VSYS", 2: "GND", 3: "EN_LDO", 4: None, 5: "+3V3"}))
    fps.append(fp_sot23_5("U4", "USBLC6-2SC6", 250.0, 31.0, 0, U("sym", "U4"),
                          {1: "USB_DM", 2: "GND", 3: "USB_DP", 4: "USB_DP",
                           5: "VBUS", 6: "USB_DM"}, npins=6))
    fps.append(fp_sot23("Q1", "DMG3415U", 137.0, 31.0, 0, U("sym", "Q1"),
                        {1: "VBUS", 2: "BAT+", 3: "VSYS"}))
    # D60 is the B5819W VBUS Schottky, not a 1N4148W like the matrix diodes
    # sharing this footprint -- the value must say so or a PCB-side BOM/
    # assembly pass would stuff a 150mA signal diode into the power path.
    fps.append(fp_diode("D60", 137.0, 35.5, 0, "VSYS", "VBUS", U("sym", "D60"), val="B5819W"))
    # D60 authored on back layer by fp_diode; that's fine (Schottky on back)
    fps.append(fp_0603("R1", "5.1k", 255.8, 34.2, 90, U("sym", "R1"), "CC1", "GND"))
    fps.append(fp_0603("R2", "5.1k", 258.8, 36.2, 90, U("sym", "R2"), "CC2", "GND"))
    fps.append(fp_0603("R3", "2.0k", 216.0, 35.5, 0, U("sym", "R3"), "PROG", "GND"))
    fps.append(fp_0603("R4", "1k", 223.0, 31.0, 90, U("sym", "R4"), "VBUS", "LED_A"))
    fps.append(fp_0603("LED1", "CHG", 223.0, 27.0, 270, U("sym", "LED1"),
                       "STAT", "LED_A", led=True))
    fps.append(fp_0603("R5", "100k", 110.5, 29.5, 0, U("sym", "R5"), "EN_LDO", "GND"))
    fps.append(fp_0603("R6", "1M", 142.0, 26.0, 0, U("sym", "R6"), "BAT+", "VBAT_SENSE"))
    fps.append(fp_0603("R7", "1M", 142.0, 29.0, 0, U("sym", "R7"), "VBAT_SENSE", "GND"))
    fps.append(fp_0603("C5", "100n", 142.0, 32.0, 0, U("sym", "C5"), "VBAT_SENSE", "GND"))
    fps.append(fp_0603("C1", "4.7u", 211.0, 35.5, 0, U("sym", "C1"), "VBUS", "GND"))
    fps.append(fp_0603("C2", "4.7u", 220.5, 35.5, 0, U("sym", "C2"), "BAT+", "GND"))
    fps.append(fp_0603("C3", "1u", 117.0, 36.0, 0, U("sym", "C3"), "VSYS", "GND"))
    fps.append(fp_0603("C4", "10u", 127.0, 36.0, 0, U("sym", "C4"), "+3V3", "GND"))
    fps.append(fp_0603("C7", "10u", 145.5, 24.0, 0, U("sym", "C7"), "+3V3", "GND"))
    fps.append(fp_0603("C8", "100n", 145.5, 27.0, 0, U("sym", "C8"), "+3V3", "GND"))
    fps.append(fp_jst_sh("J2", 128.0, 27.5, 0, U("sym", "J2"), "BAT+", "GND"))
    fps.append(fp_slide("SW62", 105.0, 23.9, 0, U("sym", "SW62"),
                        {1: "VSYS", 2: "EN_LDO", 3: "GND"}))
    fps.append(fp_btn6mm("SW60", "RESET", 93.5, 27.5, 0, U("sym", "SW60"), "RUN", "GND", side="B"))
    # Was at (170.0, 27.5): that dropped SW61's 6mm body straight onto the
    # already-populated crystal/QSPI pocket -- its THT pads (2mm annular,
    # at center +/-3.25, +/-2.25, on ALL copper layers) landed at 0.000mm
    # from Y1.2 (XOUT), C14.1 (XOUT) and C34.2 (GND): three drilled shorts,
    # confirmed by the independent drc_check. The same four through-holes
    # were also the "BOOTSEL keepout" wall that route_kbd_rp2040.py's own
    # comments repeatedly cite as blocking the U1-north escape pocket
    # (XIN, QSPI_SD2/SCLK/SD3, VREG_VIN, USB_DM's long-haul). Moved to the
    # verified-empty band between C12/R11 (x<=188) and C1/U2 (x>=211):
    # courtyard 191.6-200.4 x 24-31 clears everything with >2mm margin.
    fps.append(fp_btn6mm("SW61", "BOOTSEL", 196.0, 27.5, 0, U("sym", "SW61"), "BOOTSEL", "GND", side="B"))
    fps.append(fp_0603("R11", "330", 184.0, 27.5, 0, U("sym", "R11"), "BOOTSEL", "QSPI_SS"))
    # ---- mounting holes ----
    hi = 1
    for hc in (1.5, 6.5, 9.5):
        for hr in (0.5, 3.5):
            hx, hy = key_xy(hr, hc)
            fps.append(fp_hole(f"H{hi}", hx, hy))
            hi += 1

    # ---- fiducials (see fp_fiducial) ----
    # Same three spots on both sides (both carry SMD). Verified clear:
    # (42, 135.5) sits between the bottom key row's courtyards (end at
    # y=133.7) and the board edge (y=138.5), nearest part D49 at 8.3mm;
    # (267, 135.5) bottom-right corner, nothing within 11mm; (230, 26)
    # top strip between LED1/R4 (>=7mm) and U4. Deliberately NOT in the
    # top-left corner -- that's the antenna keepout.
    for fi, (fx, fy) in enumerate([(42.0, 135.5), (267.0, 135.5), (230.0, 26.0)]):
        fps.append(fp_fiducial(f"FID{fi+1}", fx, fy, U("sym", f"FID{fi+1}")))
        fps.append(fp_fiducial(f"FID{fi+4}", fx, fy, U("sym", f"FID{fi+4}"), side="B"))

    nets_decl = "\n".join(f'  (net {i} "{n}")' for i, n in enumerate(NETS))
    b = BOARD
    edge = (f'  (gr_rect (start {b["x1"]} {b["y1"]}) (end {b["x2"]} {b["y2"]}) '
            f'(stroke (width 0.1) (type solid)) (fill none) (layer "Edge.Cuts") (uuid "{NU("edge")}"))')
    title = (f'  (gr_text "Gateron LP 5x12 - RP2040 wireless (UNVERIFIED RF section)" (at 60 134) (layer "F.SilkS") (uuid "{NU("gt")}")\n'
             f'    (effects (font (size 2 2) (thickness 0.3))))')
    tracks = ""
    # NOTE: intentionally NOT reading the shared tracks.sexp from the parent
    # directory -- that file is the original ESP32 board's routing (wrong
    # net IDs and pin positions for this variant's completely different
    # MCU/net list). This variant ships unrouted; route separately.
    tp = os.path.join(PRJDIR, "tracks_rp2040.sexp")
    if os.path.exists(tp):
        tracks = open(tp).read()
    ax, ay = 45.0, 30.0   # CYW43439 position: antenna keepout above it (y 22-26), clear of L2/C17/C18 at y=34.5
    # This zone now holds a real antenna (ANT1, see fp_antenna_johanson) --
    # so it must NOT forbid pads/footprints/tracks (an earlier version did,
    # which would have made it impossible to ever place or route an actual
    # antenna here). Real antenna keepouts keep the GROUND PLANE/POUR and
    # stitching VIAS away (both would detune the antenna); they don't
    # forbid the antenna's own footprint or its feed trace.
    zones = f'''  (zone (net 0) (net_name "") (layers "F.Cu" "B.Cu") (uuid "{NU("antzone")}") (name "antenna_keepout") (hatch edge 0.508)
    (connect_pads (clearance 0))
    (min_thickness 0.254) (filled_areas_thickness no)
    (keepout (tracks allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed))
    (fill (thermal_gap 0.508) (thermal_bridge_width 0.508))
    (polygon (pts (xy {ax-7:g} {ay-4.0:g}) (xy {ax-7:g} {BOARD["y1"]}) (xy {ax+7:g} {BOARD["y1"]}) (xy {ax+7:g} {ay-4.0:g})))
  )
'''
    for layer in ("F.Cu", "B.Cu"):
        zones += f'''  (zone (net {NETI["GND"]}) (net_name "GND") (layer "{layer}") (uuid "{NU("zone", layer)}") (hatch edge 0.5)
    (connect_pads (clearance 0.5))
    (min_thickness 0.25) (filled_areas_thickness no)
    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon (pts (xy {b["x1"]} {b["y1"]}) (xy {b["x2"]} {b["y1"]}) (xy {b["x2"]} {b["y2"]}) (xy {b["x1"]} {b["y2"]})))
  )
'''
    return f'''(kicad_pcb (version 20240108) (generator "pcbnew") (generator_version "8.0")
  (general (thickness 1.6) (legacy_teardrops no))
  (paper "A3")
  (title_block
    (title "Gateron LP 5x12 wireless keyboard -- RP2040 variant (VERIFY RF section before fab)")
    (rev "A")
  )
  (layers
    (0 "F.Cu" signal)
    (1 "In1.Cu" signal)
    (2 "In2.Cu" signal)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (40 "Dwgs.User" user "User.Drawings")
    (41 "Cmts.User" user "User.Comments")
    (42 "Eco1.User" user "User.Eco1")
    (43 "Eco2.User" user "User.Eco2")
    (44 "Edge.Cuts" user)
    (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user)
    (49 "F.Fab" user)
  )
  (setup
    (stackup
      (layer "F.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "FR4")
        (epsilon_r 4.4) (loss_tangent 0.02))
      (layer "In1.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4")
        (epsilon_r 4.4) (loss_tangent 0.02))
      (layer "In2.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "FR4")
        (epsilon_r 4.4) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.035))
      (layer "F.SilkS" (type "Top Silk Screen"))
      (layer "F.Paste" (type "Top Solder Paste"))
      (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
      (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
      (layer "B.Paste" (type "Bottom Solder Paste"))
      (layer "B.SilkS" (type "Bottom Silk Screen"))
      (copper_finish "None")
      (dielectric_constraints no)
    )
    (pad_to_mask_clearance 0)
    (allow_soldermask_bridges_in_footprints no)
    (pcbplotparams
      (layerselection 0x00010fc_ffffffff)
      (plot_on_all_layers_selection 0x0000000_00000000)
      (disableapertmacros no)
      (usegerberextensions no)
      (usegerberattributes yes)
      (usegerberadvancedattributes yes)
      (creategerberjobfile yes)
      (dashed_line_dash_ratio 12.000000)
      (dashed_line_gap_ratio 3.000000)
      (svgprecision 4)
      (plotframeref no)
      (viasonmask no)
      (mode 1)
      (useauxorigin no)
      (hpglpennumber 1)
      (hpglpenspeed 20)
      (hpglpendiameter 15.000000)
      (pdf_front_fp_property_popups yes)
      (pdf_back_fp_property_popups yes)
      (dxfpolygonmode yes)
      (dxfimperialunits yes)
      (dxfusepcbnewfont yes)
      (psnegative no)
      (psa4output no)
      (plotreference yes)
      (plotvalue yes)
      (plotfptext yes)
      (plotinvisibletext no)
      (sketchpadsonfab no)
      (subtractmaskfromsilk no)
      (outputformat 1)
      (mirror no)
      (drillshape 1)
      (scaleselection 1)
      (outputdirectory "")
    )
  )
{nets_decl}
{"".join(fps)}
{edge}
{title}
{tracks}
{zones})
'''

# ============================================================ project ======
def build_pro():
    return json.dumps({
        "board": {
            "3dviewports": [],
            "design_settings": {
                "defaults": {},
                "rules": {
                    "min_clearance": 0.15,
                    "min_copper_edge_clearance": 0.3,
                    "min_hole_clearance": 0.25,
                    "min_track_width": 0.15,
                    "min_via_diameter": 0.5,
                },
            },
            "layer_presets": [], "viewports": [],
        },
        "boards": [], "cvpcb": {"equivalence_files": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{PROJ}.kicad_pro", "version": 1},
        "net_settings": {
            "classes": [{
                "name": "Default", "priority": 2147483647,
                "clearance": 0.2, "track_width": 0.25,
                "via_diameter": 0.6, "via_drill": 0.3,
                "microvia_diameter": 0.3, "microvia_drill": 0.1,
                "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
                "diff_pair_via_gap": 0.25,
                "bus_width": 12, "line_style": 0, "wire_width": 6,
                "pcb_color": "rgba(0, 0, 0, 0.000)",
                "schematic_color": "rgba(0, 0, 0, 0.000)",
            }],
            "meta": {"version": 3},
        },
        "pcbnew": {"last_paths": {}, "page_layout_descr_file": ""},
        "schematic": {
            "annotate_start_num": 0, "drawing": {},
            "legacy_lib_dir": "", "legacy_lib_list": [],
            "meta": {"version": 1},
        },
        "sheets": [[ROOT_UUID, "Root"]],
        "text_variables": {},
    }, indent=2)

# ============================================================ main =========
def main():
    sch = build_schematic()
    pcb = build_pcb()
    pro = build_pro()
    for name, content in [(f"{PROJ}.kicad_sch", sch), (f"{PROJ}.kicad_pcb", pcb),
                          (f"{PROJ}.kicad_pro", pro)]:
        with open(os.path.join(PRJDIR, name), "w") as f:
            f.write(content)
        print(f"wrote {name}  ({len(content)//1024} kB)")
    # quick structural check: balanced parens outside strings
    for name in (f"{PROJ}.kicad_sch", f"{PROJ}.kicad_pcb"):
        t = open(os.path.join(PRJDIR, name)).read()
        depth = 0; instr = False; mind = 99
        for ch in t:
            if ch == '"':
                instr = not instr
            elif not instr:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    mind = min(mind, depth)
        print(f"{name}: paren depth end={depth} (must be 0), min={mind}")
        assert depth == 0 and mind >= 0

if __name__ == "__main__":
    main()

# ==================================================== project libraries ====
def export_libs():
    pretty = os.path.join(PRJDIR, "kbd.pretty")
    os.makedirs(pretty, exist_ok=True)
    empty = {}
    items = [
        ("SW_Gateron_KS33_HS", fp_gateron("REF**", 0, 0, None, None, None)),
        ("D_SOD-123_Back", fp_diode("REF**", 0, 0, 0, None, None, None)),
        ("ESP32-C6-MINI-1", fp_esp32("REF**", 0, 0, None, empty)),
        ("USB_C_Receptacle_HRO_TYPE-C-31-M-12", fp_usbc("REF**", 0, 0, 0, None, empty)),
        ("SOT-23-5", fp_sot23_5("REF**", "SOT-23-5", 0, 0, 0, None, empty)),
        ("SOT-23-6", fp_sot23_5("REF**", "SOT-23-6", 0, 0, 0, None, empty, npins=6)),
        ("SOT-23", fp_sot23("REF**", "SOT-23", 0, 0, 0, None, empty)),
        ("RC_0603", fp_0603("REF**", "0603", 0, 0, 0, None, None, None)),
        ("RC_0402", fp_0402("REF**", "0402", 0, 0, 0, None, None, None)),
        ("RC_0201", fp_0201("REF**", "0201", 0, 0, 0, None, None, None)),
        ("LED_0603", fp_0603("REF**", "LED", 0, 0, 0, None, None, None, led=True)),
        ("JST_SH_SM02B_2pin_Back", fp_jst_sh("REF**", 0, 0, 0, None, None, None)),
        ("SW_Slide_MSK12C02", fp_slide("REF**", 0, 0, 0, None, empty)),
        ("SW_PUSH_6mm_THT", fp_btn6mm("REF**", "SW", 0, 0, 0, None, None, None)),
        ("MountingHole_M2", fp_hole("REF**", 0, 0)),
        ("FIDUCIAL_1MM", fp_fiducial("REF**", 0, 0, None)),
        ("RP2040_QFN56", fp_rp2040("REF**", 0, 0, None, empty)),
        ("FLASH_USON8", fp_flash8("REF**", 0, 0, 0, None, empty)),
        ("XTAL_3225", fp_crystal_smd("REF**", "XTAL", 0, 0, 0, None, None, None)),
        ("CYW43439_WLBGA63", fp_cyw43439("REF**", 0, 0, None, empty)),
        ("SK6812MINI_E", fp_sk6812mini("REF**", 0, 0, 0, None, empty)),
        ("ANT_JOHANSON_2450AT18B100", fp_antenna_johanson("REF**", 0, 0, 0, None, None)),
    ]
    for name, body in items:
        # strip instance placement, keep local geometry; body starts with header
        body = body.replace('(at 0 0)\n', '(at 0 0)\n', 1)
        txt = body.strip()
        assert txt.startswith('(footprint')
        # rename footprint id: strip "kbd:" prefix, add version header
        txt = txt.replace(f'(footprint "kbd:{name}"',
                          f'(footprint "{name}" (version 20240108) (generator "pcbnew")', 1)
        with open(os.path.join(pretty, f"{name}.kicad_mod"), "w") as f:
            f.write(txt + "\n")
    # symbol library
    sym = build_lib_symbols().replace('(symbol "kbd:', '(symbol "')
    with open(os.path.join(PRJDIR, "kbd.kicad_sym"), "w") as f:
        f.write(f'(kicad_symbol_lib (version 20231120) (generator "kicad_symbol_editor") (generator_version "8.0")\n{sym})\n')
    with open(os.path.join(PRJDIR, "fp-lib-table"), "w") as f:
        f.write('(fp_lib_table\n  (version 7)\n  (lib (name "kbd")(type "KiCad")(uri "${KIPRJMOD}/kbd.pretty")(options "")(descr "project keyboard footprints"))\n)\n')
    with open(os.path.join(PRJDIR, "sym-lib-table"), "w") as f:
        f.write('(sym_lib_table\n  (version 7)\n  (lib (name "kbd")(type "KiCad")(uri "${KIPRJMOD}/kbd.kicad_sym")(options "")(descr "project keyboard symbols"))\n)\n')
    print(f"wrote kbd.pretty ({len(items)} footprints), kbd.kicad_sym, lib tables")

main_orig = main
def main():
    main_orig()
    export_libs()

if __name__ == "__main__":
    pass
main()

#!/usr/bin/env python3
"""Route the RP2040 variant keyboard PCB.

Adapted from route_kbd.py (which routes the ESP32-C6 board). The generic
engine below (item parsing, A* router, clearance checks, connectivity
healer, emit) is unchanged from that script -- it doesn't reference
anything ESP32-specific. What's rewritten is run_routes(): the ESP32-C6-
MINI-1 module's escape-stub pattern doesn't apply to the RP2040 (different
chip, different package, different pin numbers/positions), and several
subsystems here don't exist on the ESP32 board at all (CYW43439, QSPI
flash, RP2040 crystal, antenna matching, the 59-LED RGB chain).

The USB/charger/battery/LDO section IS reused near-verbatim: U1-U4, J1,
J2, Q1, D60, SW60, SW61 all sit at IDENTICAL positions on both boards
(confirmed by direct coordinate comparison), since only the MCU footprint
itself changed between variants, not the surrounding power/USB circuitry.

KNOWN LIMITATION -- read before assuming full routing: the CYW43439 (U6)
is a WLBGA-63 package at 0.4mm ball pitch. A standard via (0.6mm diameter)
physically cannot fit between adjacent balls at that pitch. The U6 fanout
section now hand-routes every ball with a legal straight-ray escape
(outer columns/rows plus missing-ball channels): 8 nets are FULLY routed
ball-to-part (XTAL XON/XOP, XTAL_VDD1P2, VDD1P5, VOUT_LNLDO, VOUT_3P3,
BT_VCO_VDD, WLRF_ANT), and PA_VDD/VSYS reach the chip through one of
their two balls (H1/B7; the redundant M1/F7 balls are boxed in). Still
split after this pass -- with committed escape stubs where reachable:
  - BT_UART_RXD/TXD/RTS_N + BT_DEV_WAKE/BT_HOST_WAKE: the U6-side stub
    exists, but the U1-side E-fan stage tips are sealed inside the
    crystal pocket by the XIN/XOUT/VBAT/BOOTSEL weave (routed earlier,
    and fragile -- see the minimum-system section). Finish manually or
    rework the E-side pocket.
  - CYW_SR_VLX, CYW_BT_IF_VDD: stubbed; their A* chains starve on the
    shared west/north via corridors (sequential greed -- each routed
    net consumes a slot the next one needed).
  - BT_UART_CTS_N (B2), BT_REG_ON (E6), CYW_BTFM_PLL_VDD (F2),
    +3V3 (F6), CYW_VOUT_CLDO (C6/D3/G4): balls geometrically sealed at
    0.4mm pitch -- these genuinely need via-in-pad/microvia fab (HDI).

Clearance target: 0.2 mm copper-copper, 0.3 mm hole-copper, 0.45 mm edge.
"""
import math, heapq, sys, os
import numpy as np
import sexpdata
from sexpdata import Symbol

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import importlib.util
spec = importlib.util.spec_from_file_location("gen", os.path.join(HERE, "generate_kbd_rp2040.py"))
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)
NETI, KEYS, key_pos, BOARD = gen.NETI, gen.KEYS, gen.key_pos, gen.BOARD
PITCH, KX0, KY0 = gen.PITCH, gen.KX0, gen.KY0

CL = 0.2          # copper-copper clearance
CLH = 0.3         # hole-copper clearance
W_SIG = 0.25
W_PWR = 0.3
W_RF = 0.4        # antenna feed trace, 50-ohm on this board's 4-layer
                  # stackup, referenced to In1.Cu 0.2104mm below F.Cu
                  # (Hammerstad-Jensen, see generate_kbd_rp2040.py header)
                  # -- NOT the old 2L board's 3.0mm figure.
VIA_R = 0.3       # via outer radius
VIA_DRILL = 0.3
STEP = 0.2

PWR_NETS = {"VBUS", "VSYS", "BAT+", "+3V3", "GND", "DVDD"}
RF_NETS = {"WLRF_ANT", "WLRF_ANT_MID"}

def width_for(net):
    if net in RF_NETS:
        return W_RF
    return W_PWR if net in PWR_NETS else W_SIG

# ---------------------------------------------------------------- items ----
items = []

def kids(n, name):
    return [x for x in n if isinstance(x, list) and x and x[0] == Symbol(name)]
def kid(n, name):
    k = kids(n, name)
    return k[0] if k else None

def rot_pt(px, py, deg):
    t = math.radians(deg)
    return (px*math.cos(t) + py*math.sin(t), -px*math.sin(t) + py*math.cos(t))

PCBFILE = os.path.join(HERE, "gateron_lp_kbd_rp2040/gateron_lp_kbd_rp2040.kicad_pcb")
pcb = sexpdata.loads(open(PCBFILE).read())
pad_pos = {}   # (ref,padnum) -> (x,y,layerset)
for fp in kids(pcb, "footprint"):
    ref = [str(pr[2]) for pr in kids(fp, "property") if str(pr[1]) == "Reference"][0]
    at = kid(fp, "at")
    fx, fy = float(at[1]), float(at[2])
    frot = float(at[3]) if len(at) > 3 else 0
    for p in kids(fp, "pad"):
        num = str(p[1])
        ptype = str(p[2])
        shape = str(p[3])
        pat = kid(p, "at")
        px, py = float(pat[1]), float(pat[2])
        prot = float(pat[4]) if len(pat) > 4 else (float(pat[3]) if len(pat) > 3 else 0)
        dx, dy = rot_pt(px, py, frot)
        gx, gy = fx + dx, fy + dy
        sz = kid(p, "size")
        sx, sy = float(sz[1]), float(sz[2])
        nt = kid(p, "net")
        net = str(nt[2]) if nt else None
        lay = " ".join(str(t) for t in (kid(p, "layers") or []))
        if ptype == "np_thru_hole":
            items.append(("hole", "*", gx, gy, sx/2, None))
            continue
        if ptype == "thru_hole":
            layers = "*"
        elif "B.Cu" in lay:
            layers = "B"
        else:
            layers = "F"
        if shape in ("rect", "roundrect", "oval"):
            if abs(prot % 180) == 90:
                sx, sy = sy, sx
            if shape == "oval":
                items.append(("circ", layers, gx, gy, max(sx, sy)/2, net))
            else:
                items.append(("rect", layers, gx, gy, sx/2, sy/2, net))
        else:
            items.append(("circ", layers, gx, gy, max(sx, sy)/2, net))
        pad_pos[(ref, num)] = (gx, gy, layers)
        if ptype == "thru_hole":
            dr = kid(p, "drill")
            if dr:
                vals = [float(v) for v in dr[1:]
                        if not isinstance(v, (Symbol, list))]
                if vals:
                    items.append(("hole", "*", gx, gy, max(vals)/2, net))
    # Edge.Cuts board cutouts (e.g. the SK6812MINI-E reverse-mount
    # footprint's own light-transmission slot) are real holes cut through
    # the fiberglass -- a trace routed across one has no board material to
    # sit on. This engine only understands circular obstacles, so rather
    # than doing full polygon/arc clearance math, treat each footprint's
    # Edge.Cuts geometry as one conservative circumscribing circle
    # (centered on the footprint's own origin, radius = the farthest
    # Edge.Cuts point from it) -- over-blocks a little around the cutout's
    # corners, never under-blocks.
    ec_pts = []
    for shape_name in ("fp_line", "fp_arc"):
        for el in kids(fp, shape_name):
            lay = kid(el, "layer")
            if not lay or str(lay[1]) != "Edge.Cuts":
                continue
            for key in ("start", "mid", "end"):
                pt = kid(el, key)
                if pt:
                    ec_pts.append((float(pt[1]), float(pt[2])))
    if ec_pts:
        r = max(math.hypot(px, py) for px, py in ec_pts)
        items.append(("hole", "*", fx, fy, r, None))

# antenna keepout (copper forbidden both layers) -- see the zone in
# generate_kbd_rp2040.py's build_pcb: x 38-52, y 22-26 (board top edge)
ANT = (38.0, BOARD["y1"], 52.0, 26.0)

# CYW43439 (U6) footprint bbox -- routing must not attempt to enter this;
# see the file header re: via-in-pad. U6 center (45,30), body ~2.4x4.4mm,
# pad courtyard +-1.45 x +-2.45 (see fp_cyw43439 in generate_kbd_rp2040.py).
U6_BBOX = (45.0 - 1.6, 30.0 - 2.6, 45.0 + 1.6, 30.0 + 2.6)

# U1's escape-fan region (all 4 sides' staircase stubs live in roughly
# x:143-165, y:24-38). VIAS only (not tracks -- the staircase stubs
# legitimately run through here) are forbidden in this zone: without it,
# a later net's long-haul A* search can find it cheaper to backtrack into
# this crowded area to drop a via than to continue toward open space,
# which then physically blocks an EARLIER-escaped-but-not-yet-routed
# pin's own stub (confirmed by tracing exactly which segment blocked a
# failing route: another row net's own path, routed moments earlier).
U1_ESCAPE_NOVIA = (143.0, 24.0, 165.0, 38.0)

segs_out = []   # (layer, x1,y1,x2,y2, w, net)
vias_out = []   # (x, y, net)
skipped_nets = []  # nets intentionally left as a stub (U6 BGA fanout)
heal_failed = []   # nets heal_all() could not fully reconnect

def add_seg(layer, x1, y1, x2, y2, net, w=None):
    w = w or width_for(net)
    segs_out.append((layer, x1, y1, x2, y2, w, net))
    items.append(("seg", layer, x1, y1, x2, y2, w/2, net))

def add_via(x, y, net):
    vias_out.append((x, y, net))
    items.append(("via", "*", x, y, VIA_R, net))
    items.append(("hole", "*", x, y, VIA_DRILL/2, net))

# ============================================ 1. matrix pre-route ==========
# KEYS/key_pos/PITCH/BOARD are identical between the ESP32 and RP2040
# variants (confirmed by direct comparison), so the matrix's physical
# layout hasn't moved at all. What HAS changed (4-layer conversion): the
# shared ROW/COL trunk buses now live on the new inner layers (In1.Cu for
# ROW, In2.Cu for COL) instead of B.Cu/F.Cu, to free up the outer layers
# in the matrix zone -- that's where the LED chain, QSPI escape, and
# several other previously-congested nets live. Each key's own diode/
# switch pad is still a B.Cu SMD pad (can't change that, it's the part's
# own footprint), so every key now needs a via where its short B.Cu stub
# meets the inner-layer trunk -- ROW gets one of these per key (COL
# already had one, previously bridging B.Cu to F.Cu, now bridging B.Cu to
# In2.Cu instead; a standard through via connects all four layers, so no
# other change is needed there). The trunk's own hand-off point to the
# deterministic escape fanout (w_side_fanout/s_side_col_fanout, both still
# F.Cu-only) also needs a new via per column, since trunk and fanout no
# longer share a layer at that junction; ROW doesn't need an equivalent
# new via there because w_side_fanout already places one at each row's
# westmost trunk point (must_via(tx, ROWY[r], net) in that function).
COLX = {}
for c in range(12):
    COLX[c] = KX0 + c*PITCH + 6.475
ROWY = {r: KY0 + r*PITCH - 3.6 for r in range(5)}

# col4's own row-via (x-8.5 = 117.7) sits only 0.3mm from ROW4's deep
# W-side fanout lane at x=118.0 (w_side_fanout's WEST list) -- a straight
# via there fails clearance against ROW4's long F.Cu vertical for every
# OTHER row that shares this column (confirmed by must_clear_seg raising
# for ROW4 at (118.0, 41.3)-(118.0, 122.6)). Jog those rows' vias 1.8mm
# east (to 119.5, still on the same In1 trunk segment, which runs
# uninterrupted from col3's node at 98.65 to col5's at 136.75) to clear
# both ROW4's lane (118.0) and ROW3's shorter one (116.0, doesn't reach
# this far south anyway but kept clear for margin). Row 4's own col4 via
# ALSO needs a jog (west, not east) -- w_side_fanout places its own via
# for ROW4 right at (118.0, ROWY[4]) (must_via(tx, ROWY[r], net) for the
# ROW branch), and same-net hole-vs-via clearance is NOT exempted by
# item_clear (only hole-vs-segment is), so this key's unjogged via at
# 117.7 fails against that hole even though both are net ROW4 (confirmed
# by must_via raising for ROW4 at (118.0, 122.6), blocked by the hole at
# (117.7, 122.6)).
ROW_VIA_JOG = {(0, 4): 1.8, (1, 4): 1.8, (2, 4): 1.8, (3, 4): 1.8, (4, 4): -1.0}

for (r, c, u2) in KEYS:
    x, y = key_pos(r, c, u2)
    knet = f"N_R{r}C{c}"
    add_seg("B", x-8.5, y+2.635, x-8.275, y+4.7, knet, W_SIG)
    add_seg("B", x-8.5, y-0.635, x-8.5, ROWY[r], f"ROW{r}", W_SIG)
    jog = ROW_VIA_JOG.get((r, c), 0.0)
    if jog:
        add_seg("B", x-8.5, ROWY[r], x-8.5+jog, ROWY[r], f"ROW{r}", W_SIG)
    add_via(x-8.5+jog, ROWY[r], f"ROW{r}")
    add_seg("B", x+6.475, y+5.75, x+6.475, y+8.4, f"COL{c}", W_SIG)
    add_via(x+6.475, y+8.4, f"COL{c}")

for r in range(5):
    xs = sorted(key_pos(rr, cc, uu)[0] for (rr, cc, uu) in KEYS if rr == r)
    pts = [x-8.5 for x in xs]
    for a, b in zip(pts, pts[1:]):
        add_seg("In1", a, ROWY[r], b, ROWY[r], f"ROW{r}", W_SIG)

for c in range(12):
    rows_c = [r for (r, cc, u2) in KEYS if cc == c]
    ylo = KY0 + max(rows_c)*PITCH + 8.4
    xt = COLX[c]
    net = f"COL{c}"
    add_via(xt, 45.0, net)   # bridges In2 trunk (below) to F fanout (added later)
    if c == 5:
        add_seg("In2", xt, 45.0, xt, KY0 + 3*PITCH + 8.4, "COL5", W_SIG)
        add_seg("In2", xt, KY0 + 3*PITCH + 8.4, xt, 119.0, "COL5", W_SIG)
        add_seg("In2", xt, 119.0, 161.25, 119.0, "COL5", W_SIG)
        add_seg("In2", 161.25, 119.0, 161.25, KY0 + 4*PITCH + 8.4, "COL5", W_SIG)
    elif c == 6:
        add_seg("In2", xt, 45.0, xt, KY0 + 3*PITCH + 8.4, "COL6", W_SIG)
    else:
        add_seg("In2", xt, 45.0, xt, ylo, net, W_SIG)

PRE_ROUTE_SEGS = len(segs_out)
PRE_ROUTE_VIAS = len(vias_out)

# ============================================ 2. A* router =================
# Unchanged from route_kbd.py -- fully generic, references nothing board-
# specific beyond BOARD/ANT/items which are set up above.
X0, Y0 = BOARD["x1"], BOARD["y1"]
NX = int((BOARD["x2"]-X0)/STEP) + 1
NY = int((BOARD["y2"]-Y0)/STEP) + 1

def cell(x, y):
    return (round((x-X0)/STEP), round((y-Y0)/STEP))
def coord(ix, iy):
    return (X0 + ix*STEP, Y0 + iy*STEP)

def raster(mask, it, expand, x0i, y0i, x1i, y1i):
    kind = it[0]
    if kind == "rect":
        _, _, cx, cy, hw, hh, _ = it
        xa, xb = cx-hw-expand, cx+hw+expand
        ya, yb = cy-hh-expand, cy+hh+expand
    elif kind in ("circ", "hole", "via"):
        _, _, cx, cy, r = it[:5]
        xa, xb = cx-r-expand, cx+r+expand
        ya, yb = cy-r-expand, cy+r+expand
    else:
        _, _, x1, y1, x2, y2, hw, _ = it
        xa, xb = min(x1, x2)-hw-expand, max(x1, x2)+hw+expand
        ya, yb = min(y1, y2)-hw-expand, max(y1, y2)+hw+expand
    ia = max(x0i, int(math.ceil((xa-X0)/STEP - 1e-9)))
    ib = min(x1i, int(math.floor((xb-X0)/STEP + 1e-9)))
    ja = max(y0i, int(math.ceil((ya-Y0)/STEP - 1e-9)))
    jb = min(y1i, int(math.floor((yb-Y0)/STEP + 1e-9)))
    if ia > ib or ja > jb:
        return
    if kind in ("circ", "hole", "via"):
        rr = it[4] + expand
        xs = X0 + np.arange(ia, ib+1)*STEP - it[2]
        ys = Y0 + np.arange(ja, jb+1)*STEP - it[3]
        d2 = xs[:, None]**2 + ys[None, :]**2
        mask[ia-x0i:ib-x0i+1, ja-y0i:jb-y0i+1] |= d2 <= rr*rr
    elif kind == "rect":
        mask[ia-x0i:ib-x0i+1, ja-y0i:jb-y0i+1] = True
    else:
        x1, y1, x2, y2, hw = it[2], it[3], it[4], it[5], it[6]
        rr = hw + expand
        if abs(x1-x2) < 1e-9 or abs(y1-y2) < 1e-9:
            mask[ia-x0i:ib-x0i+1, ja-y0i:jb-y0i+1] = True
        else:
            xs = X0 + np.arange(ia, ib+1)*STEP
            ys = Y0 + np.arange(ja, jb+1)*STEP
            dx, dy = x2-x1, y2-y1
            L2 = dx*dx + dy*dy
            for i, xv in enumerate(xs):
                t = np.clip(((xv-x1)*dx + (ys-y1)*dy)/L2, 0, 1)
                d2 = (x1 + t*dx - xv)**2 + (y1 + t*dy - ys)**2
                mask[ia-x0i+i, ja-y0i:jb-y0i+1] |= d2 <= rr*rr

def layers_of(it):
    return it[1]

def build_masks(net, hw, region):
    x0i, y0i, x1i, y1i = region
    shp = (x1i-x0i+1, y1i-y0i+1)
    bF = np.zeros(shp, bool)
    bB = np.zeros(shp, bool)
    bV = np.zeros(shp, bool)
    for it in items:
        inet = it[-1] if it[0] != "hole" else it[5]
        kind = it[0]
        if kind == "hole":
            e_v = CLH + VIA_R
            if inet != net or inet is None:
                e_t = CLH + hw
                raster(bF, ("circ", "*", it[2], it[3], it[4]), e_t, *region)
                raster(bB, ("circ", "*", it[2], it[3], it[4]), e_t, *region)
            raster(bV, ("circ", "*", it[2], it[3], it[4]), e_v, *region)
            continue
        same = (inet == net and inet is not None)
        e_t = CL + hw
        e_v = CL + VIA_R
        lay = layers_of(it)
        if not same:
            if lay in ("F", "*"):
                raster(bF, it, e_t, *region)
            if lay in ("B", "*"):
                raster(bB, it, e_t, *region)
            raster(bV, it, e_v, *region)
    ant = ("rect", "*", (ANT[0]+ANT[2])/2, (ANT[1]+ANT[3])/2,
           (ANT[2]-ANT[0])/2, (ANT[3]-ANT[1])/2, None)
    for m, e in ((bF, hw), (bB, hw), (bV, VIA_R)):
        raster(m, ant, e, *region)
    # keep general routing out of U6's own BGA footprint (via-in-pad only)
    u6 = ("rect", "*", (U6_BBOX[0]+U6_BBOX[2])/2, (U6_BBOX[1]+U6_BBOX[3])/2,
          (U6_BBOX[2]-U6_BBOX[0])/2, (U6_BBOX[3]-U6_BBOX[1])/2, None)
    for m, e in ((bF, hw), (bB, hw), (bV, VIA_R)):
        raster(m, u6, e, *region)
    # U1 escape zone: vias forbidden, tracks still allowed (see comment on
    # U1_ESCAPE_NOVIA above)
    esc = ("rect", "*", (U1_ESCAPE_NOVIA[0]+U1_ESCAPE_NOVIA[2])/2,
           (U1_ESCAPE_NOVIA[1]+U1_ESCAPE_NOVIA[3])/2,
           (U1_ESCAPE_NOVIA[2]-U1_ESCAPE_NOVIA[0])/2,
           (U1_ESCAPE_NOVIA[3]-U1_ESCAPE_NOVIA[1])/2, None)
    raster(bV, esc, VIA_R, *region)
    inset = 0.45
    for m, e in ((bF, hw), (bB, hw), (bV, VIA_R)):
        lo_x = int(math.ceil((BOARD["x1"]+inset+e-X0)/STEP))
        hi_x = int(math.floor((BOARD["x2"]-inset-e-X0)/STEP))
        lo_y = int(math.ceil((BOARD["y1"]+inset+e-Y0)/STEP))
        hi_y = int(math.floor((BOARD["y2"]-inset-e-Y0)/STEP))
        if lo_x > x0i:
            m[:min(lo_x, x1i+1)-x0i, :] = True
        if hi_x < x1i:
            m[max(hi_x+1, x0i)-x0i:, :] = True
        if lo_y > y0i:
            m[:, :min(lo_y, y1i+1)-y0i] = True
        if hi_y < y1i:
            m[:, max(hi_y+1, y0i)-y0i:] = True
    bV |= bF | bB
    return bF, bB, bV

def astar(net, p1, l1, p2, l2, margin=14.0):
    hw = width_for(net)/2
    xa = min(p1[0], p2[0]) - margin
    xb = max(p1[0], p2[0]) + margin
    ya = min(p1[1], p2[1]) - margin
    yb = max(p1[1], p2[1]) + margin
    x0i = max(0, int((xa-X0)/STEP))
    x1i = min(NX-1, int((xb-X0)/STEP))
    y0i = max(0, int((ya-Y0)/STEP))
    y1i = min(NY-1, int((yb-Y0)/STEP))
    region = (x0i, y0i, x1i, y1i)
    bF, bB, bV = build_masks(net, hw, region)
    blocked = {"F": bF, "B": bB}
    s = cell(*p1)
    t = cell(*p2)
    sl = 0 if l1 == "F" else 1
    tl = 0 if l2 == "F" else 1
    LN = ["F", "B"]
    def rel(c):
        return (c[0]-x0i, c[1]-y0i)
    for cc in (s, t):
        rc = rel(cc)
        if not (0 <= rc[0] < bF.shape[0] and 0 <= rc[1] < bF.shape[1]):
            raise RuntimeError(f"{net}: endpoint outside region")
    start = (s[0], s[1], sl)
    goal = (t[0], t[1], tl)
    srcF = np.zeros(bF.shape, bool)
    srcB = np.zeros(bF.shape, bool)
    from shapely.geometry import Point as _P
    comps, _, _ = net_components(net)
    p1g = _P(p1[0], p1[1])
    best = None
    for local, gidx, gs in comps:
        from shapely.ops import unary_union
        d = unary_union(gs).distance(p1g)
        if best is None or d < best[0]:
            best = (d, gidx)
    src_items = [items[i] for i in best[1]] if best and best[0] < 0.5 else []
    for it in src_items:
        lay = it[1]
        if lay in ("F", "*"):
            raster(srcF, it, 0.0, *region)
        if lay in ("B", "*"):
            raster(srcB, it, 0.0, *region)
    def h(n):
        return (abs(n[0]-goal[0]) + abs(n[1]-goal[1])) + 40*(1 if n[2] != goal[2] else 0)
    came = {}
    gsc = {start: 0}
    openq = [(h(start), 0, start, None)]
    layermask = {0: bF, 1: bB}
    for lyr, sm in ((0, srcF), (1, srcB)):
        for (rx, ry) in np.argwhere(sm):
            if layermask[lyr][rx, ry]:
                continue
            nsrc = (rx + x0i, ry + y0i, lyr)
            if nsrc not in gsc:
                gsc[nsrc] = 0
                heapq.heappush(openq, (h(nsrc), 0, nsrc, None))
    found = False
    it_count = 0
    while openq:
        f, gcur, node, prev = heapq.heappop(openq)
        if node in came:
            continue
        came[node] = prev
        if node == goal:
            found = True
            break
        it_count += 1
        if it_count > 2500000:
            break
        ix, iy, il = node
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx_, ny_ = ix+dx, iy+dy
            if not (x0i <= nx_ <= x1i and y0i <= ny_ <= y1i):
                continue
            nb = (nx_, ny_, il)
            if nb in came:
                continue
            rc = (nx_-x0i, ny_-y0i)
            if blocked[LN[il]][rc] and (nx_, ny_) != t and (nx_, ny_) != s:
                continue
            ng = gcur + 1
            if ng < gsc.get(nb, 1e18):
                gsc[nb] = ng
                heapq.heappush(openq, (ng + h(nb), ng, nb, node))
        nb = (ix, iy, 1-il)
        if nb not in came:
            rc = (ix-x0i, iy-y0i)
            if not bV[rc]:
                ng = gcur + 40
                if ng < gsc.get(nb, 1e18):
                    gsc[nb] = ng
                    heapq.heappush(openq, (ng + h(nb), ng, nb, node))
    if not found:
        raise RuntimeError(f"A* failed for {net}: {p1}{l1} -> {p2}{l2}")
    path = []
    n = goal
    while n is not None:
        path.append(n)
        n = came[n]
    path.reverse()
    out_end_first = coord(path[0][0], path[0][1])
    out_end_last = coord(path[-1][0], path[-1][1])
    started_at_p1 = (path[0][0], path[0][1]) == (s[0], s[1])
    if started_at_p1 and (abs(out_end_first[0]-p1[0]) > 1e-6 or abs(out_end_first[1]-p1[1]) > 1e-6):
        add_seg(l1, p1[0], p1[1], out_end_first[0], out_end_first[1], net)
    i = 0
    while i < len(path)-1:
        j = i
        if path[i+1][2] != path[i][2]:
            add_via(*coord(path[i][0], path[i][1]), net)
            i += 1
            continue
        dx = path[i+1][0]-path[i][0]
        dy = path[i+1][1]-path[i][1]
        while (j+1 < len(path) and path[j+1][2] == path[i][2]
               and path[j+1][0]-path[j][0] == dx and path[j+1][1]-path[j][1] == dy):
            j += 1
        a = coord(path[i][0], path[i][1])
        b = coord(path[j][0], path[j][1])
        add_seg(LN[path[i][2]], a[0], a[1], b[0], b[1], net)
        i = j
    if abs(out_end_last[0]-p2[0]) > 1e-6 or abs(out_end_last[1]-p2[1]) > 1e-6:
        add_seg(l2, p2[0], p2[1], out_end_last[0], out_end_last[1], net)
    return True

def pp(ref, num):
    x, y, lay = pad_pos[(ref, num)]
    return (x, y), ("B" if lay == "B" else "F")

def route_chain(net, pts, margin=14.0):
    for (a, la), (b, lb) in zip(pts, pts[1:]):
        last = None
        for m in (margin, margin+8, margin+18, 42, 60, 80, 100, 130):
            try:
                astar(net, a, la, b, lb, m)
                last = None
                break
            except RuntimeError as e:
                last = e
        if last:
            raise last
        print(f"  routed {net}: {a} -> {b}")

def try_route_chain(net, pts, margin=14.0):
    """like route_chain but records a skip instead of raising, for the
    known-unroutable U6 BGA hop."""
    try:
        route_chain(net, pts, margin)
        return True
    except RuntimeError as e:
        skipped_nets.append((net, str(e)))
        print(f"  SKIPPED {net}: {e}")
        return False

# Per-pin depth increment (a "staircase" -- see escape_fan docstring).
# Must be a multiple of STEP (0.2mm): pin positions are grid-aligned, but
# a non-aligned depth offset produces an escape point that isn't --
# cell() then rounds it to the nearest grid center, silently shifting the
# point by up to half a step (0.1mm), which is enough to tip an
# already-marginal clearance check into a false violation (confirmed by
# comparing a raw-coordinate distance check against build_masks'
# rasterized result for the same point and finding they disagreed).
ESCAPE_DEPTH0 = 0.8
ESCAPE_DEPTH_STEP = 0.4

W_ESCAPE = 0.1    # narrow trace for the tight-pitch initial escape stub only.

def escape_fan(pin_nets, side, depth0=ESCAPE_DEPTH0, depth_step=ESCAPE_DEPTH_STEP):
    """pin_nets: ordered list of (pin_num, net) in physical pin sequence
    along one side of U1. side: 'W','S','E','N' -- outward escape
    direction.

    Two things had to be solved here, discovered by direct debugging
    (tracing exactly which item blocked a specific failing route):

    1. At 0.4mm pin pitch, parallel escape stubs at the design's normal
       0.25mm trace width can't fit side by side (needs 0.45mm pitch).
       Fixed with a narrow 0.1mm trace for this initial stub only --
       0.4mm pin pitch then clears the 0.3mm needed with real margin
       (0.15mm, tried first, landed EXACTLY on the boundary -- a
       floating-point tie that failed in practice, not genuine margin).

    2. An earlier version also dropped each pin to the back layer via a
       via immediately after this stub, so each of the ~12 pins per side
       needed a DIFFERENT via depth to keep via-to-via clearance (needs
       ~0.8mm, much more than the trace-to-trace 0.3mm above) -- but
       packing that many vias into a few mm of board next to U1 left each
       pin boxed into an isolated pocket only a few cells wide (confirmed
       by flood-filling the reachable region from a failing pin's escape
       point: 16 cells, versus hundreds of thousands available on the
       board). Fixed by not using a via here at all -- stay on the front
       layer with a per-pin staircase depth (each pin's stub is 0.4mm
       (one pin pitch) longer than the last), which only needs to clear
       the much smaller 0.3mm trace-to-trace requirement, and gives the
       long-haul A* router genuine room to maneuver instead of a solid
       wall of identical-length parallel stubs. The long-haul route
       decides on its own, via normal A* via-placement, where and whether
       to change layers -- see the "re-surface" comment where this is
       called for ROW/COL nets specifically.

    Returns {net: ((x,y), 'F')} staging points for route_chain."""
    dv = {"W": (-1, 0), "E": (1, 0), "N": (0, -1), "S": (0, 1)}[side]
    stage = {}
    for i, (num, net) in enumerate(pin_nets):
        x, y, _ = pad_pos[("U1", num)]
        depth = depth0 + i * depth_step
        ex, ey = x + dv[0]*depth, y + dv[1]*depth
        add_seg("F", x, y, ex, ey, net, W_ESCAPE)
        stage[net] = ((ex, ey), "F")
    return stage

def must_clear_seg(layer, x1, y1, x2, y2, net, w):
    hw = w/2
    if not clear_for_seg(layer, x1, y1, x2, y2, net, hw):
        raise RuntimeError(f"deterministic seg violates clearance: {net} {layer} "
                            f"({x1},{y1})-({x2},{y2}) w={w}")
    add_seg(layer, x1, y1, x2, y2, net, w)

def must_via(x, y, net):
    if not clear_for_via(x, y, net):
        raise RuntimeError(f"deterministic via violates clearance: {net} at ({x},{y})")
    add_via(x, y, net)

def _find_via(net, x0, y0, max_r, w=W_ESCAPE, x_min=None, y_min=None):
    """Radial search from (x0,y0) for the nearest point that clears a via
    on every layer AND is reachable from (x0,y0) via a 2-segment F-layer
    L-path (either ordering). Commits the escape jog + via and returns
    (x,y) on success. x_min/y_min, if given, discard candidates west/
    north of them -- useful when the near side is known to be a dead
    end (e.g. a long fixed wall) and searching it first would just
    waste candidates."""
    import math
    step = 0.1
    candidates = []
    for d in range(1, int(max_r/step)+1):
        rad = d*step
        n_ang = max(8, int(rad*30))
        for a in range(n_ang):
            ang = 2*math.pi*a/n_ang
            x = round(x0 + rad*math.cos(ang), 2)
            y = round(y0 + rad*math.sin(ang), 2)
            candidates.append((rad, x, y))
    candidates.sort()
    for rad, x, y in candidates:
        if x_min is not None and x < x_min:
            continue
        if y_min is not None and y < y_min:
            continue
        if not clear_for_via(x, y, net):
            continue
        if (clear_for_seg("F", x0, y0, x0, y, net, w/2) and
                clear_for_seg("F", x0, y, x, y, net, w/2)):
            must_clear_seg("F", x0, y0, x0, y, net, w)
            must_clear_seg("F", x0, y, x, y, net, w)
            must_via(x, y, net)
            return (x, y)
        if (clear_for_seg("F", x0, y0, x, y0, net, w/2) and
                clear_for_seg("F", x, y0, x, y, net, w/2)):
            must_clear_seg("F", x0, y0, x, y0, net, w)
            must_clear_seg("F", x, y0, x, y, net, w)
            must_via(x, y, net)
            return (x, y)
    raise RuntimeError(f"no legal via found for {net} near ({x0},{y0}) within {max_r}mm")

def _highway(net, src, dst, layer, w=None):
    """2-segment L-path (either ordering) between two already-via'd
    points on a given layer. Commits and returns True on success."""
    if w is None:
        w = width_for(net)
    sx, sy = src; dx, dy = dst
    if clear_for_seg(layer, sx, sy, dx, sy, net, w/2) and clear_for_seg(layer, dx, sy, dx, dy, net, w/2):
        must_clear_seg(layer, sx, sy, dx, sy, net, w)
        must_clear_seg(layer, dx, sy, dx, dy, net, w)
        return True
    if clear_for_seg(layer, sx, sy, sx, dy, net, w/2) and clear_for_seg(layer, sx, dy, dx, dy, net, w/2):
        must_clear_seg(layer, sx, sy, sx, dy, net, w)
        must_clear_seg(layer, sx, dy, dx, dy, net, w)
        return True
    return False

def escape_jog(stage, net, nx, ny):
    """narrow manual jog away from a too-close neighboring escape stub,
    for a net whose raw escape point has no legal A* step in any
    direction at normal trace width (see QSPI_SD0/SCLK docs in
    run_routes). Returns the new ((x,y),'F') staging point."""
    (x, y), lay = stage[net]
    must_clear_seg(lay, x, y, nx, ny, net, W_ESCAPE)
    pt = ((nx, ny), lay)
    stage[net] = pt
    return pt

def w_side_fanout(stage):
    """Deterministic (non-search) fanout for U1's W-side ROW0-4/COL0-6
    escape stubs down to the matrix trunk.

    Why not A* here: every one of these 12 nets starts from a tightly
    clustered set of escape points (all within ~4.4mm of each other,
    since they're all pins on the same side of U1) and needs to reach a
    target that, for 10 of the 12 nets, is FAR to the west; A* is free to
    pick whichever path is locally cheapest, and that repeatedly meant
    backtracking into another not-yet-routed pin's own escape stub
    (confirmed by tracing the exact blocking segment on several
    consecutive failures -- fixing one such conflict reliably surfaced a
    structurally identical one next door). A hand-planned layout removes
    the search entirely: paths are laid out so they simply cannot cross.

    The core fact that makes a crossing-free layout possible: COL0-4 and
    ROW0-4 all have targets WEST of the whole escape cluster, so for any
    two of these nets A and B, A's horizontal only threatens to cross B's
    vertical if A's escape point lies west of B's target -- which, given
    all ten targets are west of the entire cluster, reduces to "A's own
    escape point is farther west than B's" (a fixed fact of pin order,
    not of routing choice). Assigning each net's turn-depth (how far down
    it travels before going horizontal) in the SAME order as pin index
    guarantees a net's own vertical is always gone (already turned)
    before a farther-reaching net's horizontal sweeps past it. COL5/COL6
    break this pattern (their targets are just east of the cluster, not
    west), so they're routed on the opposite copper layer (F, vs. the
    west group's B) -- different layers can't clash regardless of
    geometry, sidestepping the west/east conflict entirely instead of
    trying to interleave a consistent ordering across both directions
    (verified by hand that no single per-net depth assignment satisfies
    both groups simultaneously -- the west group's own requirement and
    the east group's own requirement contradict each other for any pair
    that reaches back across the whole cluster).

    Every placement below is verified against the existing clearance
    checker (the same one `stitch_gnd` uses) before being committed, so a
    wrong assumption raises immediately with the offending coordinates
    rather than silently producing a DRC violation.
    """
    # west group: turn-depth assigned in pin-list order (ROW0..COL4) --
    # deepest first, matching the derivation above.
    WEST = [("ROW0", 134.0, "ROW"), ("ROW1", 136.0, "ROW"), ("ROW2", 138.0, "ROW"),
            ("ROW3", 116.0, "ROW"), ("ROW4", 118.0, "ROW"),
            ("COL0", COLX[0], "COL"), ("COL1", COLX[1], "COL"),
            ("COL2", COLX[2], "COL"), ("COL3", COLX[3], "COL"),
            ("COL4", COLX[4], "COL")]
    ROWNUM = {"ROW0": 0, "ROW1": 1, "ROW2": 2, "ROW3": 3, "ROW4": 4}
    # ROW0-4's own lanes (41.3-44.5) pass directly over real board cutouts
    # in row0's own LED footprints (now correctly modeled on B.Cu per the
    # real KiCad reverse-mount part -- see generate_kbd_rp2040.py's
    # fp_sk6812mini): every row0 LED sits at the same y=43.975, radius
    # ~2.23mm, blocking every copper layer since these are real holes
    # through the board, not pads. col5's hole (x=145.25) is in the path
    # of ROW0-2/COL5/COL6; col4's (x=126.2) is also in ROW3's and ROW4's
    # path (their targets, 116/118, are far enough west to reach it).
    #
    # Several earlier approaches failed: a same-layer south detour
    # (staircase around the hole, still on B) kept reopening the
    # crossing-free ordering this whole function depends on, now against
    # each other's detours too; a shared-depth In2 hop (single Y for
    # everyone) still crossed each other's dive/rise verticals whenever
    # one net's escape or target point fell inside another's crossing
    # span; descending straight to In2 on F from the raw escape point
    # (skipping the short north jog) crosses every OTHER net's own short
    # escape stub, since those stubs all reach back to the same U1 edge
    # x and only differ by 0.4mm in y (the same "farther-reaching net
    # must already have turned" rule this function's main invariant
    # exists for, just one layer over).
    #
    # What actually works: keep the standard short "jog north 0.2mm on F,
    # via to B" step from the main invariant (so the long vertical never
    # touches another net's escape stub), descend on B (not to lane_y,
    # but to this net's own dedicated dive_y), via to In2 for the
    # horizontal crossing (In2 has nothing but sparse column-trunk
    # verticals here), then rise BACK UP on In2 (not B -- B is where
    # COL0-4's own lanes live) to lane_y, then via to F. The specific
    # depths below were found by solving net-by-net, in the order that
    # exposed each new conflict, against the real clearance checker --
    # not derived by a clean formula, because the constraint (which
    # net's span contains which other net's escape/target point) isn't
    # uniform: ROW3's span is the widest and nests everyone else, but
    # COL6 partially overlaps it from the other direction, and ROW0's
    # own span partially contains ROW1/ROW2/COL5's target points despite
    # ROW0 not being widest overall. Re-deriving by hand a second time
    # if this ever needs to change is not recommended -- rebuild this
    # via the same net-by-net incremental search instead (patch
    # must_clear_seg/must_via to record-and-continue, add one net at a
    # time, verify against the real accumulated items before moving to
    # the next), and process DIVE_ORDER (not WEST's own order) when
    # solving, since later nets' searches depend on earlier ones already
    # being committed.
    DIVE_Y = {"ROW3": 34.2, "ROW4": 35.0, "ROW0": 35.8, "ROW1": 36.6, "ROW2": 37.4}
    DIVE_ORDER = ["ROW3", "ROW4", "ROW0", "ROW1", "ROW2"]
    RANK = {net: i for i, (net, _, _) in enumerate(WEST)}
    TX = {net: tx for net, tx, _ in WEST}
    escapes = {}
    for rank, (net, tx, kind) in enumerate(WEST):
        (ex, ey), _ = stage[net]
        # nudge the via 0.3mm north of the escape point before dropping it:
        # the next-deeper pin's own escape stub runs 0.4mm south of here
        # (one pin pitch), only 0.4mm from a raw via -- short of the ~0.55mm
        # a via needs from a neighboring track. Shifting north opens that to
        # 0.7mm; the shallower neighbor's stub doesn't reach this far west
        # in the first place (its own depth is shorter), so there's nothing
        # to hit in that direction.
        vy = ey - 0.2
        # COL4's escape point sits right on top of C5's pad (a nearby
        # VBAT_SENSE decoupling cap, unrelated to this net) -- the north
        # shift above runs straight into it. Jog a little further west
        # first, at the pin's own height (clear of every other net's
        # stub, which all live at other pins' own heights), then do the
        # same north shift from there.
        if net == "COL4":
            ex2 = ex - 3.1
            must_clear_seg("F", ex, ey, ex2, ey, net, W_ESCAPE)
            ex = ex2
        must_clear_seg("F", ex, ey, ex, vy, net, W_ESCAPE)
        escapes[net] = (ex, vy)

    for net in DIVE_ORDER:
        ex, vy = escapes[net]
        # 0.8mm apart: a via at one lane needs ~0.625mm clearance from a
        # neighboring lane's track (CL+VIA_R+hw = 0.2+0.3+0.125), so 0.5mm
        # spacing (tried first) put a target via right on top of the next
        # lane's own highway track.
        lane_y = 44.5 - RANK[net] * 0.8   # rank0 (ROW0) deepest .. rank9 (COL4) shallowest
        tx = TX[net]
        dive_y = DIVE_Y[net]
        must_via(ex, vy, net)
        must_clear_seg("B", ex, vy, ex, dive_y, net, W_SIG)
        must_via(ex, dive_y, net)
        must_clear_seg("In2", ex, dive_y, tx, dive_y, net, W_SIG)
        must_clear_seg("In2", tx, dive_y, tx, lane_y, net, W_SIG)
        must_via(tx, lane_y, net)
        r = ROWNUM[net]
        must_clear_seg("F", tx, lane_y, tx, ROWY[r], net, W_SIG)
        must_via(tx, ROWY[r], net)
        print(f"  routed {net}: In2 crossing at y={dive_y}, lane (F) at y={lane_y}")

    for rank, (net, tx, kind) in enumerate(WEST):
        if net in DIVE_Y:
            continue
        ex, vy = escapes[net]
        lane_y = 44.5 - rank * 0.8
        must_via(ex, vy, net)
        must_clear_seg("B", ex, vy, ex, lane_y, net, W_SIG)
        must_clear_seg("B", ex, lane_y, tx, lane_y, net, W_SIG)
        must_via(tx, lane_y, net)
        if kind == "COL":
            must_clear_seg("F", tx, lane_y, tx, 45.0, net, W_SIG)
        else:
            r = ROWNUM[net]
            must_clear_seg("F", tx, lane_y, tx, ROWY[r], net, W_SIG)
            must_via(tx, ROWY[r], net)
        print(f"  routed {net}: deterministic W-side lane (B) at y={lane_y}")

    # east group: COL5/COL6 -- targets are just EAST of the escape
    # cluster, the opposite direction from the west group above, so they
    # stay on F for their own escape/lane (never touching B, to avoid the
    # west/east conflict). COL6 escapes deeper (smaller ex) than COL5, so
    # -- mirroring the west group's own rule exactly -- COL6 gets the
    # SHALLOWER lane and COL5 the deeper one.
    #
    # Both cross row0 LED light-transmission cutouts. COL6 dives straight
    # from its own escape point to a dedicated In2 depth (41.2, safely
    # north of every hole in its path), crosses on In2, rises on In2 to
    # its own lane_y (42.4 -- nudged down from an initial 41.8 once that
    # value was found to put COL6's own target via too close to COL7's
    # lane, from s_side_col_fanout, one function down), then via to F.
    #
    # COL5 needed substantially more: its raw escape point sits wedged
    # between COL4's escape stub (just north) and COL6's own escape stub
    # (just south), only 0.4mm from each -- no via fits there at all. A
    # ~1.6mm west jog clears both (and clears COL4's own via and the
    # VBUS decoupling pad a bit further west, both confirmed by direct
    # coordinate search, not guessed). From there: F jog north 0.2mm, via
    # to B, short descend on B to a shallow dive_y=27.0 (chosen to clear
    # every ROW/COL0-4 via and lane in this immediate area -- all of
    # which pack the 28-41mm y band solid with no gaps, confirmed by
    # scanning it directly), via to In1 (NOT In2 -- In2 is where COL6's
    # own across/rise live, and COL5's target x=151.725 falls inside
    # COL6's crossing span; NOT F for the rise either -- COL7's own
    # escape pad/stub/lane, from s_side_col_fanout, occupies the entire
    # F-layer column at this x from y=27 to y=41.35). In1 turned out to
    # be essentially empty along this whole path -- confirmed by a
    # direct full-height clearance scan before committing to it, not
    # assumed because "it's a third layer". Across and rise both happen
    # on In1, all the way up to ly=44.0, then a single via back to F.
    lane_y = {"COL6": 42.4, "COL5": 44.0}
    EAST = [("COL6", COLX[6]), ("COL5", COLX[5])]
    DIVE_Y_EAST = {"COL6": 41.2, "COL5": 27.0}
    for net, tx in EAST:
        (ex, ey), _ = stage[net]
        ly = lane_y[net]
        if net == "COL6":
            dive_y = DIVE_Y_EAST[net]
            must_clear_seg("F", ex, ey, ex, dive_y, net, W_SIG)
            must_via(ex, dive_y, net)
            must_clear_seg("In2", ex, dive_y, tx, dive_y, net, W_SIG)
            must_clear_seg("In2", tx, dive_y, tx, ly, net, W_SIG)
            must_via(tx, ly, net)
            must_clear_seg("F", tx, ly, tx, 45.0, net, W_SIG)
            print(f"  routed {net}: In2 crossing at y={dive_y}, lane (F) at y={ly}")
            continue
        # COL5: jog west 1.6mm to clear COL4's/COL6's escape stubs (and
        # COL4's via, and the VBUS pad a bit further west) before doing
        # anything else.
        ex1 = ex - 1.6
        must_clear_seg("F", ex, ey, ex1, ey, net, W_ESCAPE)
        # south here, not north like every other jog in this function --
        # COL6's own escape stub sits just north of this point, so a
        # north nudge (the usual move) runs straight into it; south is
        # clear since ROW3's own In2 crossing (the next thing south of
        # here) is still 0.8mm+ away.
        vy = ey + 0.2
        must_clear_seg("F", ex1, ey, ex1, vy, net, W_ESCAPE)
        must_via(ex1, vy, net)
        dive_y = DIVE_Y_EAST[net]
        must_clear_seg("B", ex1, vy, ex1, dive_y, net, W_SIG)
        must_via(ex1, dive_y, net)
        must_clear_seg("In1", ex1, dive_y, tx, dive_y, net, W_SIG)
        must_clear_seg("In1", tx, dive_y, tx, ly, net, W_SIG)
        must_via(tx, ly, net)
        must_clear_seg("F", tx, ly, tx, 45.0, net, W_SIG)
        print(f"  routed {net}: In1 crossing at y={dive_y}, lane (F) at y={ly}")

def s_side_col_fanout(stage):
    """Deterministic fanout for COL7-11 (U1's S side) down to their column
    trunks. Same root cause as w_side_fanout: all five escape from a
    tightly clustered set of points (all S-side pins, x 152-157) and all
    target far east, so A* kept finding it cheaper to cut back through a
    neighboring, not-yet-routed pin's own escape stub (confirmed the same
    way as the W-side bug -- traced the exact blocking segment back to
    COL7's own A*-chosen path sitting 0.45mm from COL8's escape point,
    well under the ~0.625mm a track needs from a via/point there).

    Unlike the W-side nets, these all reach in the SAME direction (east),
    so there's no via/layer-split needed at all: every net's horizontal
    just needs to sit deeper (larger y) than every S-side pin's own
    escape stub, which tops out at 39.45mm (RGB_GPIO's, the deepest of
    the eleven S-side pins) -- once a horizontal is below that, it can't
    cross any stub regardless of which x's it passes over, and distinct
    nets' horizontals (each its own y) never cross each other either.
    """
    # COL7 has the smallest escape-point x (least far from U1) of this
    # group, COL11 the largest -- so COL7 needs the DEEPEST lane and COL11
    # the shallowest (whichever net's own x is farthest east must already
    # be a finished horizontal, at a shallower y, by the time a
    # farther-reaching net's vertical -- one with a smaller x -- passes
    # through that height on its way down to an even deeper lane).
    for i, net in enumerate(["COL11", "COL10", "COL9", "COL8", "COL7"]):
        (ex, ey), _ = stage[net]
        # narrow (W_ESCAPE) width, not the normal W_SIG: at full width,
        # 0.45mm mutual clearance x 5 nets doesn't fit between the
        # RGB_GPIO stub (39.45) and COL6/COL5's lanes (41.3+) -- narrow
        # only needs 0.3mm apart, which does fit.
        lane_y = 39.75 + i * 0.4     # all clear of RGB_GPIO's stub (39.45)
        tx = COLX[int(net[3:])]
        must_clear_seg("F", ex, ey, ex, lane_y, net, W_ESCAPE)
        must_clear_seg("F", ex, lane_y, tx, lane_y, net, W_ESCAPE)
        must_clear_seg("F", tx, lane_y, tx, 45.0, net, W_SIG)
        print(f"  routed {net}: deterministic S-side lane (F) at y={lane_y}")

def run_routes():
    # ================= RP2040 (U1) escape stubs =================
    # Real pin positions transcribed from the generated board (see the
    # pad-dump used to write this script).
    stage = {}
    # W side uses a deeper depth step (0.8mm vs the default 0.4mm) than the
    # other three sides: every one of these 12 nets gets a via right at its
    # escape point (see w_side_fanout), and adjacent vias need ~0.8mm
    # center-to-center clearance -- 0.4mm depth step alone only gives
    # sqrt(0.4^2+0.4^2)=0.57mm between neighbors (0.4mm pin pitch plus 0.4mm
    # depth stagger), not enough. 0.8mm depth step gives sqrt(0.8^2+0.4^2)
    # =0.89mm, clearing it with real margin.
    stage.update(escape_fan([
        ("2", "ROW0"), ("3", "ROW1"), ("4", "ROW2"), ("5", "ROW3"), ("6", "ROW4"),
        ("7", "COL0"), ("8", "COL1"), ("9", "COL2"), ("11", "COL3"), ("12", "COL4"),
        ("13", "COL5"), ("14", "COL6")], "W", depth_step=0.8))
    stage.update(escape_fan([
        ("15", "COL7"), ("16", "COL8"), ("17", "COL9"), ("18", "COL10"),
        ("20", "XIN"), ("21", "XOUT"), ("24", "SWCLK"), ("25", "SWDIO"),
        ("26", "RUN"), ("27", "COL11"), ("28", "RGB_GPIO")], "S"))
    stage.update(escape_fan([
        ("29", "BT_REG_ON"), ("30", "BT_DEV_WAKE"), ("31", "BT_UART_RXD"),
        ("32", "BT_UART_TXD"), ("34", "BT_UART_RTS_N"), ("35", "BT_UART_CTS_N"),
        ("38", "VBAT_SENSE"), ("40", "BT_HOST_WAKE")], "E"))
    # QSPI pins are NOT in this fan -- their stubs get hand-picked depths
    # in the QSPI section below (each tip must land at a specific y that
    # matches U5's pad rows / wrap lanes, not a uniform staircase).
    stage.update(escape_fan([
        ("44", "VREG_VIN"), ("46", "USB_DM"), ("47", "USB_DP")], "N"))

    # escape_fan already lands every net on the front layer, which is
    # nearly empty here except column trunks -- the long-haul A* travels
    # there and only dives to the back layer (row-trunk territory) once,
    # right at each target, via its own normal via-placement logic.

    # ---- row/column fanout: staged escape point -> matrix trunk ----
    # ROW0-4 and COL0-6 (W side) are hand-routed, not A*-searched -- see
    # w_side_fanout's docstring for why (the search kept backtracking into
    # other not-yet-routed pins' own escape stubs).
    w_side_fanout(stage)
    s_side_col_fanout(stage)

    # QSPI_* deterministic placement (and, right after it, VBAT_SENSE's
    # own first hop) both need to happen before XOUT/XIN get their own
    # A*-searched shot at this same U1-north/east neighborhood -- see
    # each block's own comment below for why. Moved ahead of the
    # "RP2040 minimum system" section (which used to come first) for
    # exactly that reason.
    #
    # ---- QSPI fanout: U5 sits directly WEST of U1's QSPI pin bank ----
    # (moved in generate_kbd_rp2040.py from (166.5,35) -- see the comment
    # there. The old south-east placement forced every QSPI net around
    # U1's east side; the lane/elevator system that required (SD1's F
    # lane at y=23.75 spanning x 152.55-170, plus B/F elevators at
    # x=170-174) sealed the whole U1-north pocket and made QSPI_SD2/
    # SCLK/SD3, XIN, VREG_VIN and USB_DM/DP unroutable.)
    #
    # Stub depths are hand-picked per net instead of escape_fan's uniform
    # staircase (parallel verticals at 0.4mm pin pitch never collide, so
    # any depth assignment is legal; only the horizontals need distinct,
    # planned y's):
    #   SD3/SCLK/SD0 tips land EXACTLY on U5's east-column pad rows
    #   (pins 7/6/5 at y 23.75/24.25/24.75) -> three dead-straight lanes.
    #   SS/SD1/SD2 tips land SOUTH of U5's pad field (y 26.15/25.75/
    #   25.35) -> each runs west under U5, turns north on U5's west side
    #   (x 147.2/147.55/147.9), and enters its west-column pad (pins
    #   1/2/3 at y 23.25/23.75/24.25) from the west. Nesting is
    #   crossing-free by construction: a net's own vertical spans only
    #   [its pad y, its lane y], and every other net's horizontals sit
    #   outside that span (checked pairwise; must_clear_seg re-verifies
    #   every segment against the real accumulated board at emit time).
    QSPI_STUBS = [
        ("56", "QSPI_SS",   26.15),
        ("55", "QSPI_SD1",  25.75),
        ("54", "QSPI_SD2",  25.35),
        ("53", "QSPI_SD0",  24.75),   # = U5 pad 5 row
        ("52", "QSPI_SCLK", 24.25),   # = U5 pad 6 row
        ("51", "QSPI_SD3",  23.75),   # = U5 pad 7 row
    ]
    for num, net, tipy in QSPI_STUBS:
        px, py, _ = pad_pos[("U1", num)]
        add_seg("F", px, py, px, tipy, net, W_ESCAPE)
        stage[net] = ((px, tipy), "F")
    # east column: straight lanes (tip y == pad row y by construction)
    for net, padnum in (("QSPI_SD3", "7"), ("QSPI_SCLK", "6"), ("QSPI_SD0", "5")):
        (ex, ey), _ = stage[net]
        (tx, ty), _ = pp("U5", padnum)
        must_clear_seg("F", ex, ey, tx, ty, net, W_ESCAPE)
        print(f"  routed {net}: straight lane y={ey} into U5.{padnum}")
    # west column: south lane -> vertical on U5's west flank -> east leg
    for net, padnum, vx in (("QSPI_SS", "1", 147.2), ("QSPI_SD1", "2", 147.55),
                            ("QSPI_SD2", "3", 147.9)):
        (ex, ey), _ = stage[net]
        (tx, ty), _ = pp("U5", padnum)
        must_clear_seg("F", ex, ey, vx, ey, net, W_ESCAPE)
        must_clear_seg("F", vx, ey, vx, ty, net, W_ESCAPE)
        must_clear_seg("F", vx, ty, tx, ty, net, W_ESCAPE)
        print(f"  routed {net}: SW wrap via x={vx} into U5.{padnum}")
    # +3V3 feed for the relocated U5/C15: a dedicated F lane at y=22.7
    # from C7's own +3V3 pad, riding the strip between the board edge
    # (copper floor 22.45) and everything U5-related (the wrap verticals
    # top out at pad-row y>=23.25; U5/C15 pad tops are >=23.0/22.68 --
    # the lane lands directly ON C15 pad 1, which is the same net).
    must_clear_seg("F", 144.725, 24.0, 144.725, 22.7, "+3V3", W_SIG)
    must_clear_seg("F", 144.725, 22.7, 152.215, 22.7, "+3V3", W_SIG)
    must_clear_seg("F", 152.215, 22.7, 152.215, 23.0, "+3V3", W_SIG)
    print("  routed +3V3 edge lane C7 -> C15/U5")
    # USB_DM's two escape jogs and VREG_VIN's jog, hoisted from their
    # sections further below: they must commit before any long-haul A*
    # (QSPI_SS to R11, XIN to C13 in particular) is free to claim the
    # same corridors through the now-open pocket. VREG_VIN's jog exists
    # because its raw escape point sits 0.567mm from DVDD's pin-45/50
    # via -- too close for a normal-width A* departure.
    escape_jog(stage, "USB_DM", stage["USB_DM"][0][0], 25.4)
    escape_jog(stage, "USB_DM", 159.0, 25.4)

    # +3V3 (7 pins: 10, 22, 33, 42, 43, 48, 49) and DVDD (pin 23) are the
    # last of U1's power pins missing an escape_fan() stub -- every one
    # of them sits at 0.4mm pitch between neighbors that already have
    # their own tuned escape geometry, so a via can't be dropped at (or
    # anywhere near) the raw pad itself in most cases. Unlike DVDD's own
    # pin 23 fix attempted earlier (which kept finding a route that
    # quietly stole some OTHER net's only viable path through this same
    # neighborhood), this uses In1/In2 as dedicated "expressway" layers:
    # once a candidate via clears EVERY layer (a via is a real
    # through-hole -- it always needs clearance on all 4 layers,
    # regardless of which one the trace continues on), the actual
    # long-haul crossing happens entirely on In1/In2, which have far
    # less copper in this area than F/B do. That means each pin's fix
    # only has to solve ONE local problem (finding a legal via within
    # reach of the crowded pad) instead of also fighting for a share of
    # the same congested F/B corridor every other net here wants.
    #
    # Every via point below was found by a radial grid search against
    # the real accumulated board state (nearest first, checking BOTH
    # that the via itself is clear on all layers AND that a 2-segment
    # F-layer jog from the raw pad can reach it) -- not guessed, and not
    # reused from the earlier failed attempt. They're committed in a
    # specific order (matching the code below) because, same as
    # everywhere else in this neighborhood, committing one net's via
    # can consume the only legal via point for its own neighbor pin.
    # pin 10's own 2-segment L-path search (what _find_via tries) only
    # finds a via 9.2mm due north, at (151.73,22.82) -- the resulting
    # long straight F-layer wall at x=151.73 sits right next to QSPI_SS's
    # own escape stub (152.15,23.35, only 0.42mm away -- not enough
    # clearance for a via) and traps XIN's escape pocket down to 24
    # cells, breaking both nets. Fix: go south instead of north -- a
    # short jog to x=151.73 (clearing pin10's own crowded column), then
    # down to y=34.41 (2.5mm, vs. 9.2mm north) and back to x=151.06,
    # which is clear of both QSPI_SS's and XIN's own escape stubs.
    must_clear_seg("F", 151.1, 32.0, 151.73, 32.0, "+3V3", W_ESCAPE)
    must_clear_seg("F", 151.73, 32.0, 151.73, 34.41, "+3V3", W_ESCAPE)
    must_clear_seg("F", 151.73, 34.41, 151.06, 34.41, "+3V3", W_ESCAPE)
    must_via(151.06, 34.41, "+3V3")
    v10 = (151.06, 34.41)
    _highway("+3V3", v10, (144.725, 24.0), "In2", W_PWR)
    must_via(144.725, 24.0, "+3V3")

    v22 = _find_via("+3V3", 154.95, 34.65, 3.0)
    # lands 0.4mm short of C8's own pad -- C8 itself conflicts with
    # COL5's In1 crossing for a via -- then a short F jog the rest of
    # the way.
    _highway("+3V3", v22, (144.57, 26.32), "In2", W_PWR)
    must_via(144.57, 26.32, "+3V3")
    must_clear_seg("F", 144.57, 26.32, 144.57, 27.0, "+3V3", W_PWR)
    must_clear_seg("F", 144.57, 27.0, 144.725, 27.0, "+3V3", W_PWR)

    v23 = _find_via("DVDD", 155.35, 34.65, 6.0)
    _highway("DVDD", v23, (167.225, 33.0), "In2", W_PWR)
    must_via(167.225, 33.0, "DVDD")

    v33 = _find_via("+3V3", 158.4, 32.0, 4.0)
    # C15 moved next to U5, west of U1 (see generate_kbd_rp2040.py), so
    # the old (171.57, 34.8) landing point no longer has +3V3 copper.
    # Land on C11's own +3V3 pad instead (via-in-pad, same net). A plain
    # 2-segment _highway L can't get there on In1: DVDD's own riser
    # (x=170, y 23.5-33) walls In1 at every y in that span, so pass
    # SOUTH of its bottom end at y=34.2 with an explicit 3-segment path.
    must_clear_seg("In1", v33[0], v33[1], v33[0], 34.2, "+3V3", W_PWR)
    must_clear_seg("In1", v33[0], 34.2, 179.225, 34.2, "+3V3", W_PWR)
    must_clear_seg("In1", 179.225, 34.2, 179.225, 24.5, "+3V3", W_PWR)
    must_via(179.225, 24.5, "+3V3")

    # (Historical note: with U5 at its old south-east spot, pin 42's via
    # sat on the crystal's only viable approach and XIN was unroutable no
    # matter where the via landed. With U5 moved west and the QSPI
    # lane/elevator system gone, XIN now routes -- via the C13-first,
    # XIN-before-XOUT ordering in the minimum-system section below.)
    v42 = _find_via("+3V3", 158.4, 28.4, 4.0)
    _highway("+3V3", v42, (175.225, 24.5), "In2", W_PWR)
    must_via(175.225, 24.5, "+3V3")

    # 43/48/49 all gather onto pin 22's own via above (already a live
    # +3V3 landing point -- no new via needed, just a trace ending
    # there) rather than each reaching all the way to a cap individually.
    v43 = _find_via("+3V3", 157.35, 27.35, 2.0)
    _highway("+3V3", v43, v22, "In2", W_PWR)
    v48 = _find_via("+3V3", 155.35, 27.35, 2.0)
    _highway("+3V3", v48, v22, "In2", W_PWR)
    v49 = _find_via("+3V3", 154.95, 27.35, 2.0)
    _highway("+3V3", v49, v22, "In2", W_PWR)
    print("  routed +3V3 pins 10/22/33/42/43/48/49 and DVDD pin 23 via In1/In2 expressways")

    # DVDD pins 45/50 via gather + VREG_VIN's jog, in claim order:
    # v48/v49 (2.0mm search radius, most fragile) must land first; the
    # pin 45/50 vias (10mm radius) next -- and both before VREG_VIN's
    # fixed jog walls off the (156-158, 25.5-27.3) pocket, and before
    # XIN's now-successful A* (minimum-system section below) is free to
    # snake through the same cells. The In1 segments emitted here end at
    # (163.08, 23.5), where the C32->C33 highway (committed later, see
    # its own comment) has its own In1 lane: same net, copper overlaps,
    # no via needed at the joint. VREG_VIN's jog exists because its raw
    # escape point sits 0.567mm from DVDD's pin-45 via -- too close for
    # a normal-width A* departure.
    for pin_num, x0, y0 in (("45", 156.55, 27.35), ("50", 154.55, 27.35)):
        vx, vy = _find_via("DVDD", x0, y0, 10.0)
        must_clear_seg("In1", vx, vy, vx, 23.7, "DVDD", W_PWR)
        must_clear_seg("In1", vx, 23.7, 163.08, 23.7, "DVDD", W_PWR)
        must_clear_seg("In1", 163.08, 23.7, 163.08, 23.5, "DVDD", W_PWR)
    print("  routed DVDD pins 45/50 to C33 via a y=23.7 In1 lane north of the pocket")
    escape_jog(stage, "VREG_VIN", 158.0, 26.55)

    # (QSPI_SD2/SCLK/SD3 used to be force-skipped here -- unroutable
    # around the old south-east U5 placement. All six QSPI nets are now
    # laid out deterministically in the QSPI section above.)

    # VBAT_SENSE's escape point sits in a tiny (~2.6x1.2mm) F/B pocket
    # boxed in by neighboring U1 E-side pins on one side and the
    # crystal's own XIN/XOUT traces on the other -- confirmed via a
    # flood-fill from the escape point: only 95 grid cells reachable
    # (F+B combined, including via hops -- there is no via anywhere in
    # this pocket that clears every wall around it). The pocket itself
    # isn't a hard physical dead end, though: XIN/XOUT have plenty of
    # routing freedom and, whichever way A* happens to send them,
    # permanently wall off this exit if routed first. VBAT_SENSE's own
    # A* search escapes north through the same narrow U1-north strip
    # QSPI_SD0/SD1 use -- routing it AFTER QSPI's own fixed geometry
    # (above) lets A* find a path around that fixed copper; routing it
    # before QSPI's placement let A* wander straight through QSPI's own
    # reserved lane, and QSPI's hardcoded segments (not being adaptive)
    # then crashed instead of gracefully skipping. Must still run before
    # XIN/XOUT below, for the same pocket-walling reason.
    try_route_chain("VBAT_SENSE", [stage["VBAT_SENSE"], pp("C5", "1")], 30)

    # ================= RP2040 minimum system =================
    # XIN before XOUT, and C13 (its load cap) as the first target: XIN's
    # escape tip sits one 0.4mm pin-pitch inside XOUT's, so whichever of
    # the two routes first claims the only southern corridor out of the
    # S-side stub comb (the y>38 strip where vias become legal again --
    # everything shallower is inside U1_ESCAPE_NOVIA). XOUT's own target
    # (Y1.2, the crystal's EAST pad) is the easier one to reach second.
    # With the old order, XIN was sealed into a dead pocket every run.
    try_route_chain("XIN", [stage["XIN"], pp("C13", "1")], 20)
    try_route_chain("XIN", [pp("C13", "1"), pp("Y1", "1")], 6)
    try_route_chain("XOUT", [stage["XOUT"], pp("Y1", "2")], 20)
    try_route_chain("XOUT", [pp("Y1", "2"), pp("C14", "1")], 6)
    # QSPI_SS routed here, before RUN/BOOTSEL/+3V3 below: U5 (SPI flash) has
    # 0.5mm-pitch pads, and routing those other chains first was observed to
    # wall off the approach to U5 entirely (confirmed by re-running with
    # only the escape fanouts done -- QSPI_SCLK's own approach succeeds in
    # isolation, and fails only once RUN/QSPI_SS/BOOTSEL are routed first).
    # (single chain now: U5.1 is already tied to U1.56's stub by the
    # deterministic SW wrap in the QSPI section, so R11 only needs to
    # reach the net once -- the old second chain re-crossed the whole
    # board to connect two already-connected points.)
    try_route_chain("QSPI_SS", [stage["QSPI_SS"], pp("R11", "2")], 30)
    try_route_chain("+3V3", [pp("U5", "8"), pp("C15", "1")], 8)
    try_route_chain("RUN", [stage["RUN"], pp("R9", "1")], 30)
    try_route_chain("RUN", [pp("R9", "1"), pp("C12", "1")], 6)
    try_route_chain("RUN", [pp("C12", "1"), pp("SW60", "1")], 100)
    try_route_chain("+3V3", [pp("R9", "2"), pp("C10", "1")], 8)
    try_route_chain("+3V3", [pp("C10", "1"), pp("C11", "1")], 6)
    try_route_chain("BOOTSEL", [pp("R11", "1"), pp("SW61", "1")], 100)
    # SW61 (6mm THT push button) has 2 physical solder pads for its own
    # pin "1" -- diagonal legs at center +/-3.25 in x, per fp_btn6mm's own
    # footprint -- sharing a pad NAME doesn't make them electrically
    # joined in copper; they need their own trace like any other 2 points
    # on the same net. pp() returns the east leg (last parsed); the west
    # leg's coordinate is hardcoded here. SW61 moved (170,27.5) ->
    # (196,27.5) in generate_kbd_rp2040.py (its old THT pads shorted into
    # Y1/C14/C34), so the legs are now at (192.75,25.25)/(199.25,25.25).
    try_route_chain("BOOTSEL", [((192.75, 25.25), "F"), pp("SW61", "1")], 10)
    # DVDD pin 23 is now handled earlier (In2 expressway to C33, see the
    # comment before VBAT_SENSE above) -- pins 45/50 already had clean
    # escape stubs and route fine on their own.
    try_route_chain("DVDD", [pp("C9", "1"), pp("C32", "1")], 8)
    # C32 -> C33 stopped being a plain A* hop once BOOTSEL's own leg-to-
    # leg trace (added this session, see the BOOTSEL fix above) and the
    # new +3V3/DVDD expressway vias nearby ate into the same F/B corridor
    # -- C32's own reachable F/B pocket shrank to 653 cells, walled off
    # from C33's own (much bigger, 8025-cell) pocket by BOOTSEL's own
    # keepout circle. Same fix as everywhere else in this neighborhood:
    # a short local via near C32 (0.2mm away -- C32's own raw pad is
    # itself grazed by BOOTSEL's new leg-to-leg trace), then the
    # long-haul crossing on In1, north of BOOTSEL's keepout, then south
    # past it on the east side where it's clear.
    must_clear_seg("F", 163.225, 24.5, 163.08, 24.5, "DVDD", W_ESCAPE)
    must_clear_seg("F", 163.08, 24.5, 163.08, 24.36, "DVDD", W_ESCAPE)
    must_via(163.08, 24.36, "DVDD")
    must_clear_seg("In1", 163.08, 24.36, 163.08, 23.5, "DVDD", W_PWR)
    must_clear_seg("In1", 163.08, 23.5, 170.0, 23.5, "DVDD", W_PWR)
    must_clear_seg("In1", 170.0, 23.5, 170.0, 33.0, "DVDD", W_PWR)
    must_clear_seg("In1", 170.0, 33.0, 167.225, 33.0, "DVDD", W_PWR)
    # no via here -- C33 already has one from pin 23's own expressway
    # above, landing at this exact point; just terminate the trace there.
    #
    # U1.45/U1.50 themselves can't reach C33's via directly: the whole
    # x=[152,168]/y=[29,36] pocket between U1's N-side escapes and C33
    # is packed with other nets' own vias (+3V3 pins 22/33/43/48/49,
    # DVDD pin 23's own highway, QSPI_SD0, VBAT_SENSE, XOUT, a GND
    # keepout) -- no lane at any y in that band clears on any layer.
    # Fix: go the OTHER way, north of the pocket entirely, joining the
    # C32->C33 highway's own y=23.5 In1 lane (see above) at y=23.7 --
    # confirmed clear at that specific y for both pins (23.5 itself is
    # blocked by a BOOTSEL via at (157.3,23.0), and every y tried in the
    # 29-36 pocket is blocked somewhere along the run).
    # (the pins 45/50 via gather itself was hoisted to the early claim
    # section after the QSPI block: it must grab its via landing spots
    # in the U1-north pocket before VREG_VIN's jog and XIN's now-
    # successful A* route consume them. The In1 segs it emits join this
    # highway's own y=23.5 lane at x=163.08 -- copper overlap on the
    # same net, no via needed at the joint.)
    # C33 itself was relocated in generate_kbd_rp2040.py (168.0,24.5 ->
    # 168.0,33.0) -- its pad center used to sit 0.89mm from BOOTSEL's own
    # 1.0mm-radius through-hole pad, closer than the 1.2mm even a
    # zero-width trace needs, so no route could ever leave it in any
    # direction. That part is a genuine, permanent placement fix and
    # stays regardless of whether DVDD's own routing above ever succeeds.
    # (VREG_VIN's escape jog to (158.0, 26.55) was hoisted to the early
    # claim section after the QSPI block -- once XIN started routing
    # successfully through the reopened pocket, its A* was free to claim
    # this corridor first and the late jog crashed on clearance.)
    # Past that first via, the search still can't reach C34: x=161 is a
    # solid wall from y=23 to y=32, stacked from several different
    # nets' own copper -- QSPI_SS/QSPI_SD1 (y=22.8-23.5), a DVDD
    # crossing (y=25.5), XIN's own pad+wall (y=26-28.5), and the E-side
    # BT_*/VBAT_SENSE escape_fan cluster (y=29-32, raw pins starting at
    # x=158.4). The only clear crossings found (y=30.5, 33.5, 34.0) are
    # south of VREG_VIN's own reachable pocket, and a straight run down
    # to them hits BT_REG_ON's own raw pad directly. Left unrouted --
    # same oversaturated-neighborhood story as QSPI_SCLK/SD2/SD3 above.
    try_route_chain("VREG_VIN", [stage["VREG_VIN"], pp("C34", "1")], 20)

    # ---- SR_VLX + BT_IF_VDD: deterministic via-pairs to B ----
    # (Committed BEFORE the RGB chain: LEDD0_R's adaptive A* used to draw
    # a B-layer wall at x=47.3 crossing both lanes; deterministic first,
    # adaptive routes around it.)
    # Their A* chains starve on the shared west/north surface corridors
    # (each routed net consumes the slot the next one needed), so both
    # drop to B right at their own stubs: via #1 sits ON the stub --
    # outside the antenna zone's via ban (edge >= 0.55mm south of it)
    # and >= 0.5mm from every foreign copper item -- then a straight
    # B run under the open field south of U6, and a rise into the
    # target pad's own column. The two B lanes are staggered 0.65mm so
    # the second net's rise-via clears the first net's lane.
    must_via(45.8, 26.85, "CYW_SR_VLX")            # on A6's north stub
    must_clear_seg("B", 45.8, 26.85, 45.8, 36.7, "CYW_SR_VLX", W_SIG)
    must_clear_seg("B", 45.8, 36.7, 68.225, 36.7, "CYW_SR_VLX", W_SIG)
    must_via(68.225, 36.7, "CYW_SR_VLX")
    must_clear_seg("F", 68.225, 36.7, 68.225, 38.3, "CYW_SR_VLX", W_SIG)
    must_via(42.25, 30.2, "CYW_BT_IF_VDD")         # on G1's stub tip
    # jog east on B before descending: a vertical at x=42.25 leaves no
    # legal via column between itself and the RF feed riser (x=41.2
    # edge) for PA_VDD's under-pass below
    must_clear_seg("B", 42.25, 30.2, 43.6, 30.2, "CYW_BT_IF_VDD", W_SIG)
    must_clear_seg("B", 43.6, 30.2, 43.6, 37.35, "CYW_BT_IF_VDD", W_SIG)
    must_clear_seg("B", 43.6, 37.35, 64.225, 37.35, "CYW_BT_IF_VDD", W_SIG)
    must_via(64.225, 37.35, "CYW_BT_IF_VDD")
    must_clear_seg("F", 64.225, 37.35, 64.225, 38.3, "CYW_BT_IF_VDD", W_SIG)
    print("  routed CYW_SR_VLX + CYW_BT_IF_VDD via B-layer under-passes")
    # PA_VDD gets the third staggered underpass (lane y=38.0, vertical
    # x=41.75 -- WEST of IF's lane start so the two never cross; the
    # crossing-free rule here is the same as the M-comb's: a lane only
    # conflicts with a vertical whose x its span contains). Its old A*
    # chain was the one net the SR/IF lanes squeezed out. The F approach
    # jogs south-then-west off H1's stub tip because a via anywhere on
    # the tip itself sits 0.4mm from G1's stub / IF's via (needs 0.5).
    must_clear_seg("F", 42.95, 30.6, 42.95, 30.95, "CYW_PA_VDD", W_ESCAPE)
    must_clear_seg("F", 42.95, 30.95, 41.75, 30.95, "CYW_PA_VDD", W_ESCAPE)
    must_clear_seg("F", 41.75, 30.95, 41.75, 32.0, "CYW_PA_VDD", W_ESCAPE)
    must_via(41.75, 32.0, "CYW_PA_VDD")
    must_clear_seg("B", 41.75, 32.0, 41.75, 38.0, "CYW_PA_VDD", W_SIG)
    must_clear_seg("B", 41.75, 38.0, 48.225, 38.0, "CYW_PA_VDD", W_SIG)
    must_via(48.225, 38.0, "CYW_PA_VDD")
    must_clear_seg("F", 48.225, 38.0, 48.225, 38.3, "CYW_PA_VDD", W_SIG)
    print("  routed CYW_PA_VDD via the third (y=38.0) B-layer under-pass")


    # ================= RGB chain =================
    # RGB_GPIO's escape stub runs parallel and immediately adjacent to
    # COL11's own (wider, W_SIG) trunk trace for its entire length --
    # both are consecutive S-side escape_fan pins (0.4mm pitch) moving
    # in the same direction, and COL11 continues past its own escape
    # depth via s_side_col_fanout's deterministic matrix lane, a long
    # horizontal at y=39.75 spanning nearly the whole board width (not
    # just a local pinch). Two W_SIG (0.25mm) traces need 0.45mm pitch
    # to coexist; confirmed via astar()'s own src-item seeding (every
    # cell along RGB_GPIO's existing 0.1mm-wide escape stub is within
    # COL11's clearance zone, so the search can't leave its own escape
    # point at normal width). Fix: jog east (clears COL11's vertical
    # stub) and slightly north to y=39.3 (0.45mm from COL11's y=39.75
    # trunk -- staying at the escape stub's own y=39.45 sits exactly
    # 0.3mm away, a floating-point tie at the clearance boundary that
    # fails in practice, same issue documented in escape_fan's own
    # docstring), at the escape stub's own narrow width, before handing
    # off to the normal-width A*.
    escape_jog(stage, "RGB_GPIO", 158.4, 39.3)
    try_route_chain("RGB_GPIO", [stage["RGB_GPIO"], pp("U7", "2")], 40)
    try_route_chain("GND", [pp("U7", "1"), pp("U7", "3")], 4)
    try_route_chain("LEDD0", [pp("U7", "4"), pp("R10", "1")], 6)
    try_route_chain("VSYS", [pp("U7", "5"), pp("C19", "1")], 8)
    try_route_chain("LEDD0_R", [pp("R10", "2"), pp("RGB1", "4")], 30)
    # RGB{i} pin 3 is VSYS (real KiCad SK6812MINI-E footprint layout is
    # 1=GND, 2=DOUT, 3=VDD, 4=DIN -- see fp_sk6812mini/build_pcb's own
    # comment in generate_kbd_rp2040.py). Every VSYS hop below used to
    # reference pin 1, a leftover from before that footprint was
    # corrected to the real reverse-mount pinout this session -- pin 1
    # is GND now, so every one of these 59 hops was trying to via into a
    # GND pad and failing every time (confirmed: that's exactly why
    # heal_all() found VSYS split into ~122 disconnected components,
    # one per LED/cap, not a routing congestion problem at all).
    try_route_chain("VSYS", [pp("U7", "5"), pp("RGB1", "3")], 32)
    for i in range(1, 60):
        ref = f"RGB{i}"
        cref = f"C{100 + (i - 1)}"
        try_route_chain(f"VSYS", [pp(ref, "3"), pp(cref, "1")], 6)
        if i < 59:
            nref = f"RGB{i + 1}"
            try_route_chain(f"LEDD{i}", [pp(ref, "2"), pp(nref, "4")], 32)
            try_route_chain("VSYS", [pp(ref, "3"), pp(nref, "3")], 32)
    # ============ U6 (CYW43439) outer-ball fanout + RF feed ============
    # The WLBGA-63's 0.4mm ball pitch fits no via or trace between
    # adjacent balls, so only balls with a clear straight ray off the
    # package (outer columns/rows, plus channels through MISSING ball
    # positions) are routable on F.Cu. Everything here is deterministic
    # (must_clear_seg self-verifies at emit time) or a short stub handed
    # to A* via a staging point just outside the router's U6 bbox mask.
    # Escape stubs are W_ESCAPE (0.1mm): lateral clearance to the
    # neighbouring 0.25mm balls at 0.4mm pitch is 0.225mm.
    #
    # Balls with NO legal escape (verified against the ball map, pad
    # edge +0.19 clearance per 0.1mm trace): B2 (BT_UART_CTS_N -- the
    # single B3/A3 gap channel is taken by C3/RTS below), E6
    # (BT_REG_ON), F2 (CYW_BTFM_PLL_VDD), F6 (+3V3), C6/D3/G4
    # (CYW_VOUT_CLDO), and the interior GND balls. Those stay
    # via-in-pad/HDI territory (see the file header).
    # West stubs, ALTERNATING tip depths (42.95 / 42.25): with uniform
    # tips, each tip's exit cells sit inside the adjacent stubs' A*
    # clearance masks and the middle nets are sealed at birth -- the
    # same reason escape_fan staircases. Alternating 0.7mm clears every
    # tip's west neighbour cell (verified against the mask arithmetic:
    # adjacent-stub mask reaches tip_x - 0.075 at worst).
    for desig, net, tipx in (("A1", "BT_UART_RXD", 42.95),
                             ("B1", "BT_DEV_WAKE", 42.25),
                             ("C1", "BT_HOST_WAKE", 42.95),
                             ("F1", "CYW_BT_VCO_VDD", 42.95),
                             ("G1", "CYW_BT_IF_VDD", 42.25),
                             ("H1", "CYW_PA_VDD", 42.95)):
        (bx, by), _ = pp("U6", desig)
        must_clear_seg("F", bx, by, tipx, by, net, W_ESCAPE)
    # north stubs: A2/A6 straight out; C3 (BT_UART_RTS_N) escapes through
    # the B3+A3 missing-ball channel at x=44.6. Tips stay south of the
    # antenna-keepout mask (y >= 26.4) so A* can start there.
    for desig, net, tipy in (("A2", "BT_UART_TXD", 26.9),
                             ("A6", "CYW_SR_VLX", 26.7),
                             ("C3", "BT_UART_RTS_N", 26.5)):
        (bx, by), _ = pp("U6", desig)
        must_clear_seg("F", bx, by, bx, tipy, net, W_ESCAPE)
    # East pocket: the strip between U6's bbox and Y2 is too narrow for
    # multiple free A* starting points, so B7/C7/D6 ride a deterministic
    # LADDER out to the open top strip east of the antenna keepout:
    # each net gets a vertical on U6's east flank (0.35 pitch), an
    # eastward lane over Y2 (0.35 pitch, each 0.6 longer than the one
    # above), and a final north nib that clears every shorter lane --
    # tips land 0.6mm apart in open board at y=25.5. E7 (CYW_VOUT_3P3)
    # keeps a simple stub: its row sits below the ladder verticals and
    # escapes south/via-to-B. F7 is skipped -- same net (VSYS) as B7.
    for desig, net, vx, laney, nibx in (
            ("B7", "VSYS",           47.00, 26.30, 52.8),   # nib extended to 25.1 below
            ("C7", "CYW_VDD1P5",     47.35, 26.65, 53.4),
            ("D6", "CYW_VOUT_LNLDO", 47.70, 27.00, 54.0)):
        (bx, by), _ = pp("U6", desig)
        must_clear_seg("F", bx, by, vx, by, net, W_ESCAPE)
        must_clear_seg("F", vx, by, vx, laney, net, W_ESCAPE)
        must_clear_seg("F", vx, laney, nibx, laney, net, W_ESCAPE)
        must_clear_seg("F", nibx, laney, nibx, 25.5, net, W_ESCAPE)
    (bx, by), _ = pp("U6", "E7")
    must_clear_seg("F", bx, by, 46.9, by, "CYW_VOUT_3P3", W_ESCAPE)
    # VSYS: the B7 ladder tip continues as a deterministic F-only run to
    # SW62's own VSYS pad (pad 1) along the empty top strip -- no via,
    # so it can pass just north of the C7/D6 nib tips (y=25.1, 0.225
    # edge clearance) and needs no B corridor at all. Its old A* chain
    # to RGB1.3 needed a B descent that every staggered lane south of
    # U6 now walls off, and the healer's patch died with it. The lane
    # runs at y=23.5: 2.0mm north of the C7/D6 ladder tips (a first cut
    # at y=25.1 sat 0.4mm from them -- inside the A* clearance mask --
    # and landlocked VDD1P5's chain start), 1.75mm north of SW60's THT
    # pads, and east of the antenna zone (x >= 52.8 > its 52.0 edge).
    # The final descent at x=102.5 clears SW62's no-net west mounting
    # pad (x 100.0-101.2) by 1.3mm and lands on pad 1 at its own y.
    must_clear_seg("F", 52.8, 25.5, 52.8, 23.5, "VSYS", W_ESCAPE)
    must_clear_seg("F", 52.8, 23.5, 102.5, 23.5, "VSYS", W_SIG)
    must_clear_seg("F", 102.5, 23.5, 102.5, 25.9, "VSYS", W_SIG)
    print("  routed VSYS: B7 ladder -> SW62 pad 1 via the top strip")
    print("  emitted U6 W/N ball stubs + east-pocket ladder")

    # ---- M-row (south) comb: deterministic all the way to the pads ----
    # Same crossing-free construction as the U1-side combs: every lane
    # starts AT its own ball's x and runs east, so a ball's descent
    # never crosses a lane that begins further east; the east-most ball
    # takes the shallowest lane. North-rising terminations (M5/M4 into
    # Y2/C30 at y=30) sit west of every longer lane's end; south-dipping
    # terminations (M3/M2 into the y=34.5 cap row) cross only lanes that
    # have already ended. Lane pitch 0.32-0.36 keeps every edge-to-edge
    # gap >= 0.22 (a 0.30 pitch gives exactly 0.20 -- a float tie).
    # M1 (CYW_PA_VDD) is NOT in the comb: its net also owns H1 in the
    # west column, routed above -- one lane fewer keeps the stack clear
    # of the RF feed run at y=35.1.
    for desig, net, laney, endx, endy in (
            ("M5", "CYW_XTAL_XON",    32.60, 51.300, 30.50),  # up into Y2.2
            ("M4", "CYW_XTAL_XOP",    32.92, 53.225, 30.30),  # up into C30.1
            ("M3", "CYW_XTAL_VDD1P2", 33.24, 61.225, 34.40),  # down into C21.1
            ("M2", "CYW_VDD1P5",      33.56, 57.225, 34.40)): # down into C20.1
        (bx, by), _ = pp("U6", desig)
        must_clear_seg("F", bx, by, bx, laney, net, W_ESCAPE)
        must_clear_seg("F", bx, laney, endx, laney, net, W_ESCAPE)
        must_clear_seg("F", endx, laney, endx, endy, net, W_ESCAPE)
    print("  routed U6 M-row comb: XON/XOP/XTAL_VDD1P2/VDD1P5 to their pads")

    # ---- WLRF_ANT: ball K1 -> L2.1 -> C17.1, deterministic ----
    # L2 is rotated 270 in the generator so pad 1 (this net) faces NORTH
    # toward the chip and pad 2 (the feed side) faces SOUTH -- with the
    # old orientation this trace and the feed run below had to cross.
    # 0.1mm neck off the ball (a 0.4mm trace would violate the adjacent
    # J1 ball), then 0.4mm: south between the MID riser (x=41.4) and the
    # package's west pads, east at y=34.05 (clears M2's lane end-circle
    # by 0.24), overlapping L2.1's pad top at x=45, then on east to
    # C17.1 (same net) -- so the whole ANT node is one piece of copper.
    (k1x, k1y), _ = pp("U6", "K1")
    must_clear_seg("F", k1x, k1y, 43.15, k1y, "WLRF_ANT", W_ESCAPE)
    must_clear_seg("F", 43.15, k1y, 43.15, 34.05, "WLRF_ANT", W_RF)
    must_clear_seg("F", 43.15, 34.05, 48.515, 34.05, "WLRF_ANT", W_RF)
    # solid dips into the two pads (the run itself only grazes their top
    # edges by ~0.1mm -- not a fab-robust joint on its own). The L2.1 dip
    # stops at 34.19: its end-circle then reaches y=34.39, deep in the pad
    # (bottom edge 34.405) while keeping 0.205 to L2.2 (top edge 34.595).
    must_clear_seg("F", 45.0, 34.05, 45.0, 34.19, "WLRF_ANT", W_RF)
    must_clear_seg("F", 48.515, 34.05, 48.515, 34.3, "WLRF_ANT", W_RF)
    print("  routed WLRF_ANT: K1 -> L2.1 -> C17.1 (0.4mm RF, 0.1mm ball neck)")

    # ---- WLRF_ANT_MID feed: L2.2 -> (C18 branch) -> ANT1, deterministic --
    # Generic A* can never route this: the mask bans the whole antenna
    # keepout rect (a conservative simplification -- the real zone only
    # bans pour/vias and allows tracks) and ANT1's feed pad is inside it.
    # Path (0.4mm except the DNP C18 branch): south off L2.2, west at
    # y=35.1 (south of everything U6-related), riser north at x=41.0 --
    # (41.0 rather than 41.4: the extra 0.4mm leaves room for TWO via
    # columns between the riser and K1's riser-let, so the west-pocket
    # nets don't all fight over a single legal via slot on their way
    # down to B -- with one slot, whichever chain routed first starved
    # the rest) --
    # west of the K1 riser-let, the W-comb stub tips (42.95) and the
    # whole package -- across the keepout, then east into ANT1's FEED
    # pad. The 0.1mm branch at y=35.1 serves C18.1 (DNP tuning cap).
    # RF caveat (also in generate_kbd_rp2040.py): matching values need
    # real tuning and Johanson's free layout review should see this
    # geometry before fab.
    # 0.15mm neck off the pad: a 0.4mm attach here would violate L2.1
    # 0.49mm away (same 0201-pitch constraint as K1's ball neck)
    must_clear_seg("F", 45.0, 34.745, 45.0, 35.1, "WLRF_ANT_MID", 0.15)
    must_clear_seg("F", 45.0, 35.1, 41.0, 35.1, "WLRF_ANT_MID", W_RF)
    must_clear_seg("F", 45.0, 35.1, 52.515, 35.1, "WLRF_ANT_MID", W_ESCAPE)
    must_clear_seg("F", 52.515, 35.1, 52.515, 34.75, "WLRF_ANT_MID", W_ESCAPE)
    must_clear_seg("F", 41.0, 35.1, 41.0, 24.5, "WLRF_ANT_MID", W_RF)
    must_clear_seg("F", 41.0, 24.5, 43.65, 24.5, "WLRF_ANT_MID", W_RF)
    print("  routed WLRF_ANT_MID feed: L2.2 -> ANT1 (west riser), C18 branch")



    # ================= CYW43439-adjacent externals =================
    # (external-to-U6 parts only -- see file header re: U6's own BGA)
    # Nets whose ONLY other connection is a U6 ball (C21, C22, C23, C27,
    # C28, C29, L3-pin1) need no further routing -- there's nothing else
    # external to connect them to; the U6-side hop is the deliberate stub.
    try_route_chain("CYW_XTAL_XOP", [pp("Y2", "1"), pp("C30", "1")], 8)
    try_route_chain("CYW_XTAL_XON", [pp("Y2", "2"), pp("R13", "1")], 8)
    try_route_chain("CYW_XTAL_XON_J", [pp("R13", "2"), pp("C31", "1")], 8)
    try_route_chain("CYW_VOUT_3P3", [pp("C24", "1"), pp("R12", "1")], 8)
    try_route_chain("CYW_PA_VDD", [pp("R12", "2"), pp("C25", "1")], 8)
    try_route_chain("CYW_PA_VDD", [pp("C25", "1"), pp("C26", "1")], 8)
    try_route_chain("CYW_VDD1P5", [pp("L3", "2"), pp("C20", "1")], 10)

    # ---- A* chains: ball stubs/ladder tips to each net's copper ----
    # Runs AFTER the externals chains below: those are short constrained
    # local hops (C25<->C26 etc.) that an earlier long-haul is free to
    # squeeze out; these chains have the whole board to adapt in.
    # BT_* long-hauls go to U1's E-side escape stage points (~115mm:
    # south past the MID riser, east through the y~36-37 corridor and
    # the open top strip).
    for net, tip, target, margin in (
            ("BT_UART_RXD",   (42.95, 27.8), stage["BT_UART_RXD"],   40),
            ("BT_DEV_WAKE",   (42.25, 28.2), stage["BT_DEV_WAKE"],   40),
            ("BT_HOST_WAKE",  (42.95, 28.6), stage["BT_HOST_WAKE"],  40),
            ("BT_UART_TXD",   (44.2, 26.9),  stage["BT_UART_TXD"],   40),
            ("BT_UART_RTS_N", (44.6, 26.5),  stage["BT_UART_RTS_N"], 40),
            ("CYW_BT_VCO_VDD", (42.95, 29.8), pp("C27", "1"), 30),
            ("CYW_VDD1P5",     (53.4, 25.5),  pp("C20", "1"), 30),
            ("CYW_VOUT_LNLDO", (54.0, 25.5),  pp("C23", "1"), 40),
            ("CYW_VOUT_3P3",   (46.9, 29.4),  pp("R12", "1"), 40)):
        # both stage[...] entries and pp() results are already ((x,y), layer)
        try_route_chain(net, [(tip, "F"), target], margin)

    for net, why in (("BT_UART_CTS_N", "ball B2 sealed (B3/A3 channel taken by RTS)"),
                     ("BT_REG_ON", "ball E6 sealed by B5"),
                     ("CYW_BTFM_PLL_VDD", "ball F2 sealed by B5"),
                     ("+3V3", "ball F6 fully interior"),
                     ("CYW_VOUT_CLDO", "balls C6/D3/G4 fully interior")):
        skipped_nets.append((net, f"U6 via-in-pad/HDI required -- {why}"))
        print(f"  SKIPPED U6 ball for {net}: {why}")

    # ================= USB / charger / battery / LDO =================
    # Reused near-verbatim from route_kbd.py: U1-U4, J1, J2, Q1, D60, SW60,
    # SW61 sit at IDENTICAL positions on both board variants.
    USBX = 262.0
    for x in (USBX+0.25, USBX-0.75):
        add_seg("F", x, 29.645, x, 30.9, "USB_DP", W_SIG)
    add_seg("F", USBX-0.75, 30.9, USBX+0.25, 30.9, "USB_DP", W_SIG)
    for x in (USBX+0.75, USBX-0.25):
        add_seg("F", x, 29.645, x, 28.2, "USB_DM", W_SIG)
    add_seg("F", USBX-0.25, 28.2, USBX+0.75, 28.2, "USB_DM", W_SIG)
    add_seg("F", USBX+1.25, 29.645, USBX+1.25, 31.7, "CC1", W_SIG)
    add_seg("F", USBX-1.75, 29.645, USBX-1.75, 32.2, "CC2", W_SIG)
    add_via(USBX-1.75, 32.2, "CC2")
    add_seg("F", USBX+2.45, 30.37, USBX+2.45, 33.0, "VBUS")
    add_seg("F", USBX-2.45, 30.37, USBX-2.45, 33.0, "VBUS")
    add_seg("F", USBX-2.45, 33.0, USBX+2.45, 33.0, "VBUS")

    add_seg("F", *pad_pos[("U4","4")][:2], *pad_pos[("U4","3")][:2], "USB_DP", W_SIG)
    add_seg("F", *pad_pos[("U4","6")][:2], *pad_pos[("U4","1")][:2], "USB_DM", W_SIG)
    try_route_chain("USB_DM", [((USBX+0.75, 28.2), "F"), pp("U4", "6")], 12)
    try_route_chain("USB_DP", [((USBX-0.75, 30.9), "F"), pp("U4", "4")], 12)
    try_route_chain("VBUS", [pp("J1", "A4"), pp("U4", "5")], 14)
    try_route_chain("CC1", [((USBX+1.25, 31.7), "F"), pp("R1", "1")], 8)
    try_route_chain("CC2", [((USBX-1.75, 32.2), "B"), pp("R2", "1")], 8)
    # USB_DM's own escape point can't depart at normal width: it's
    # 0.4mm from USB_DP's own parallel escape stub (same 0.4mm-pitch
    # neighbor problem as everywhere else on U1), and a straight jog
    # east crosses DVDD's own escape stub (x=156.55, y=25.99-27.35).
    # Jog north first (to y=25.4, clear of DVDD's stub) then east to
    # x=159.0 -- confirmed clear at normal width from there. USB_DP's
    # own escape point has no such local conflict.
    #
    # Neither net can complete the long-haul hop to U4 near the USB
    # connector, though (~90mm away): the whole neighborhood around
    # U1's N-side escape cluster is only reachable via B layer (F is
    # blocked solid by DVDD/XIN/QSPI/BOOTSEL geometry), but it also
    # sits inside U1_ESCAPE_NOVIA (143-165, 24-38) -- generic A* is
    # barred from creating a via there (by design, to keep it from
    # sprinkling vias through this delicate escape fan-out), so it can
    # never bridge from the F-declared escape point down to the
    # B-reachable region. Placing that via manually (bypassing the
    # policy, as done for +3V3/DVDD/QSPI elsewhere) doesn't help either
    # -- every candidate landing point just past the zone boundary
    # (x=165-176) is itself blocked by a different net's own via or
    # wall (BOOTSEL's keepout, XOUT's pad, DVDD's pin-23 via, QSPI_SD0's
    # own B-layer elevator at x=171). Left unrouted.
    # (USB_DM's escape jogs were hoisted to right after the QSPI section:
    # with the U1-north pocket now open, QSPI_SS's own long-haul A* was
    # free to claim the exact corridor the jog needs -- claiming it
    # before any A* runs makes the jog deterministic again.)
    try_route_chain("USB_DM", [pp("U4", "1"), stage["USB_DM"]], 30)
    try_route_chain("USB_DP", [pp("U4", "3"), stage["USB_DP"]], 30)
    try_route_chain("VBUS", [pp("U4", "5"), pp("Q1", "1")], 20)
    try_route_chain("VBUS", [pp("Q1", "1"), pp("D60", "2")], 8)
    try_route_chain("VBUS", [pp("J1", "B4"), pp("U2", "4")], 10)
    try_route_chain("VBUS", [pp("U2", "4"), pp("C1", "1")], 8)
    try_route_chain("VBUS", [pp("U2", "4"), pp("R4", "1")], 8)
    try_route_chain("STAT", [pp("U2", "1"), pp("LED1", "1")], 8)
    try_route_chain("LED_A", [pp("R4", "2"), pp("LED1", "2")], 6)
    try_route_chain("PROG", [pp("U2", "5"), pp("R3", "1")], 6)
    try_route_chain("BAT+", [pp("J2", "1"), pp("Q1", "2")], 10)
    try_route_chain("BAT+", [pp("J2", "1"), pp("R6", "1")], 10)
    try_route_chain("BAT+", [pp("Q1", "2"), pp("U2", "3")], 16)
    try_route_chain("BAT+", [pp("U2", "3"), pp("C2", "1")], 8)
    try_route_chain("VSYS", [pp("Q1", "3"), pp("D60", "1")], 8)
    try_route_chain("VSYS", [pp("Q1", "3"), pp("U3", "1")], 12)
    try_route_chain("VSYS", [pp("U3", "1"), pp("C3", "1")], 8)
    try_route_chain("VSYS", [pp("U3", "1"), pp("SW62", "1")], 14)
    try_route_chain("EN_LDO", [pp("U3", "3"), pp("R5", "1")], 12)
    try_route_chain("EN_LDO", [pp("R5", "1"), pp("SW62", "2")], 8)
    try_route_chain("+3V3", [pp("U3", "5"), pp("C4", "1")], 8)
    try_route_chain("+3V3", [pp("C4", "1"), pp("C7", "1")], 12)
    try_route_chain("+3V3", [pp("C7", "1"), pp("C8", "1")], 6)
    try_route_chain("+3V3", [pp("C8", "1"), pp("U1", "1")], 30)
    # VBAT_SENSE's own escape-point hop was moved up before XIN/XOUT --
    # see the comment there. Only the two downstream hops stay here.
    try_route_chain("VBAT_SENSE", [pp("C5", "1"), pp("R7", "1")], 6)
    try_route_chain("VBAT_SENSE", [pp("R7", "1"), pp("R6", "2")], 6)

    # +3V3 as routed above forms 3 disconnected clusters -- {C10,C11,R9} (QSPI-
    # flash-area decoupling), {C4,C7,C8,U1,U3} (LDO-output cluster), {C15,U5.8}
    # (U5's own local decoupling) -- with no hop anywhere bridging them. Add the
    # 2 missing inter-cluster edges (nearest real pad pairs, confirmed clear).
    try_route_chain("+3V3", [pp("C10", "1"), pp("C15", "1")], 20)
    try_route_chain("+3V3", [pp("U1", "1"), pp("U5", "8")], 20)

def stitch_gnd():
    """place a GND via + stub next to SMD GND pads (planes carry GND)"""
    count = 0
    for fp in kids(pcb, "footprint"):
        ref = [str(pr[2]) for pr in kids(fp, "property") if str(pr[1]) == "Reference"][0]
        if ref == "U6":
            continue  # BGA -- via-in-pad only, see file header
        at = kid(fp, "at")
        fx, fy = float(at[1]), float(at[2])
        frot = float(at[3]) if len(at) > 3 else 0
        for p in kids(fp, "pad"):
            if str(p[2]) != "smd":
                continue
            nt = kid(p, "net")
            if not nt or str(nt[2]) != "GND":
                continue
            pat = kid(p, "at")
            dx, dy = rot_pt(float(pat[1]), float(pat[2]), frot)
            gx, gy = fx+dx, fy+dy
            lay = "B" if "B.Cu" in " ".join(str(t) for t in kid(p, "layers")) else "F"
            for cand in ((0, 1.3), (0, -1.3), (1.3, 0), (-1.3, 0),
                         (0, 1.8), (0, -1.8), (1.8, 0), (-1.8, 0)):
                vx, vy = gx+cand[0], gy+cand[1]
                if not (BOARD["x1"]+0.8 < vx < BOARD["x2"]-0.8 and
                        BOARD["y1"]+0.8 < vy < BOARD["y2"]-0.8):
                    continue
                if ANT[0]-0.5 < vx < ANT[2]+0.5 and vy < ANT[3]+0.5:
                    continue
                if clear_for_via(vx, vy, "GND") and clear_for_seg(lay, gx, gy, vx, vy, "GND"):
                    add_seg(lay, gx, gy, vx, vy, "GND", 0.35)
                    add_via(vx, vy, "GND")
                    count += 1
                    break
    print(f"GND stitching vias: {count}")

def dist_seg_pt(x1, y1, x2, y2, px, py):
    dx, dy = x2-x1, y2-y1
    L2 = dx*dx+dy*dy
    if L2 == 0:
        return math.hypot(px-x1, py-y1)
    t = max(0, min(1, ((px-x1)*dx+(py-y1)*dy)/L2))
    return math.hypot(x1+t*dx-px, y1+t*dy-py)

def item_clear(it, kind2, layer2, geo2, net2, need):
    inet = it[-1] if it[0] != "hole" else it[5]
    lay = it[1]
    if inet == net2 and inet is not None and (it[0] != "hole" or kind2 == "seg"):
        return True
    if it[0] != "hole" and lay != "*" and layer2 != "*" and lay != layer2:
        return True
    if it[0] == "rect":
        _, _, cx, cy, hw, hh, _ = it
        if kind2 == "circ":
            px, py, r = geo2
            ddx = max(abs(px-cx)-hw, 0)
            ddy = max(abs(py-cy)-hh, 0)
            return math.hypot(ddx, ddy) >= need + r
        else:
            x1, y1, x2, y2, r = geo2
            n = max(2, int(math.hypot(x2-x1, y2-y1)/0.15)+1)
            for i in range(n+1):
                px = x1 + (x2-x1)*i/n
                py = y1 + (y2-y1)*i/n
                ddx = max(abs(px-cx)-hw, 0)
                ddy = max(abs(py-cy)-hh, 0)
                if math.hypot(ddx, ddy) < need + r:
                    return False
            return True
    elif it[0] in ("circ", "hole", "via"):
        cx, cy, r0 = it[2], it[3], it[4]
        if kind2 == "circ":
            px, py, r = geo2
            return math.hypot(px-cx, py-cy) >= need + r + r0
        else:
            x1, y1, x2, y2, r = geo2
            return dist_seg_pt(x1, y1, x2, y2, cx, cy) >= need + r + r0
    else:
        _, _, x1, y1, x2, y2, hw0, _ = it
        if kind2 == "circ":
            px, py, r = geo2
            return dist_seg_pt(x1, y1, x2, y2, px, py) >= need + r + hw0
        else:
            a1, b1, a2, b2, r = geo2
            n = max(2, int(math.hypot(a2-a1, b2-b1)/0.15)+1)
            for i in range(n+1):
                px = a1 + (a2-a1)*i/n
                py = b1 + (b2-b1)*i/n
                if dist_seg_pt(x1, y1, x2, y2, px, py) < need + r + hw0:
                    return False
            return True

def clear_for_via(vx, vy, net):
    for it in items:
        need = CLH if it[0] == "hole" else CL
        if not item_clear(it, "circ", "*", (vx, vy, VIA_R), net, need):
            return False
    return True

def clear_for_seg(layer, x1, y1, x2, y2, net, hw=0.175):
    for it in items:
        need = CLH if it[0] == "hole" else CL
        if not item_clear(it, "seg", layer, (x1, y1, x2, y2, hw), net, need):
            return False
    return True

LAYER_NAME = {"F": "F.Cu", "B": "B.Cu", "In1": "In1.Cu", "In2": "In2.Cu"}

def emit():
    lines = []
    for i, (layer, x1, y1, x2, y2, w, net) in enumerate(segs_out):
        ln = LAYER_NAME[layer]
        lines.append(
            f'  (segment (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) '
            f'(width {w:g}) (layer "{ln}") (net {NETI[net]}) (uuid "{gen.NU("rseg", i)}"))')
    for i, (x, y, net) in enumerate(vias_out):
        lines.append(
            f'  (via (at {x:.3f} {y:.3f}) (size {VIA_R*2:g}) (drill {VIA_DRILL:g}) '
            f'(layers "F.Cu" "B.Cu") (net {NETI[net]}) (uuid "{gen.NU("rvia", i)}"))')
    with open(os.path.join(HERE, "gateron_lp_kbd_rp2040", "tracks_rp2040.sexp"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"emitted {len(segs_out)} segments, {len(vias_out)} vias")
    if skipped_nets:
        print(f"\n{len(skipped_nets)} nets NOT routed (need manual/via-in-pad, see file header):")
        for net, err in skipped_nets:
            print(f"  {net}: {err}")
    if heal_failed:
        print(f"\n{len(heal_failed)} nets NOT fully connected after healing:")
        for net, err in heal_failed:
            print(f"  {net}: {err}")

# ============================================ 3. connectivity healing ======
def item_shapely(it):
    from shapely.geometry import Point, LineString, box
    if it[0] == "rect":
        _, _, cx, cy, hw, hh, _ = it
        return box(cx-hw, cy-hh, cx+hw, cy+hh)
    if it[0] in ("circ", "via", "hole"):
        return Point(it[2], it[3]).buffer(it[4], 16)
    _, _, x1, y1, x2, y2, hw, _ = it
    return LineString([(x1, y1), (x2, y2)]).buffer(hw, 8)

def net_components(net):
    from shapely.strtree import STRtree
    idxs = [i for i, it in enumerate(items)
            if it[0] != "hole" and it[-1] == net]
    geoms = [item_shapely(items[i]) for i in idxs]
    par = {i: i for i in range(len(idxs))}
    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    tree = STRtree(geoms)
    for a in range(len(idxs)):
        la = items[idxs[a]][1]
        for b in tree.query(geoms[a].buffer(0.003)):
            b = int(b)
            if b <= a:
                continue
            lb = items[idxs[b]][1]
            if la != "*" and lb != "*" and la != lb:
                continue
            if geoms[a].distance(geoms[b]) < 0.005:
                ra, rb = find(a), find(b)
                if ra != rb:
                    par[ra] = rb
    comps = {}
    for a in range(len(idxs)):
        comps.setdefault(find(a), []).append(a)
    return [(sorted(v), [idxs[i] for i in v], [geoms[i] for i in v])
            for v in comps.values()], idxs, geoms

def astar_heal(net, src_items, tgt_items, hint_a, hint_b, margin=16.0):
    hw = width_for(net)/2
    xa = min(hint_a[0], hint_b[0]) - margin
    xb = max(hint_a[0], hint_b[0]) + margin
    ya = min(hint_a[1], hint_b[1]) - margin
    yb = max(hint_a[1], hint_b[1]) + margin
    x0i = max(0, int((xa-X0)/STEP)); x1i = min(NX-1, int((xb-X0)/STEP))
    y0i = max(0, int((ya-Y0)/STEP)); y1i = min(NY-1, int((yb-Y0)/STEP))
    region = (x0i, y0i, x1i, y1i)
    bF, bB, bV = build_masks(net, hw, region)
    lmask = {0: bF, 1: bB}
    shp = bF.shape
    srcF = np.zeros(shp, bool); srcB = np.zeros(shp, bool)
    tgtF = np.zeros(shp, bool); tgtB = np.zeros(shp, bool)
    for it in src_items:
        lay = it[1]
        if lay in ("F", "*"):
            raster(srcF, it, 0.0, *region)
        if lay in ("B", "*"):
            raster(srcB, it, 0.0, *region)
    for it in tgt_items:
        lay = it[1]
        if lay in ("F", "*"):
            raster(tgtF, it, 0.0, *region)
        if lay in ("B", "*"):
            raster(tgtB, it, 0.0, *region)
    tgt = {0: tgtF, 1: tgtB}
    gx, gy = cell(*hint_b)
    def h(n):
        return abs(n[0]-gx) + abs(n[1]-gy)
    came = {}; gsc = {}
    openq = []
    for lyr, sm in ((0, srcF), (1, srcB)):
        for (rx, ry) in np.argwhere(sm):
            if lmask[lyr][rx, ry]:
                continue
            n = (rx+x0i, ry+y0i, lyr)
            gsc[n] = 0
            heapq.heappush(openq, (h(n), 0, n, None))
    goal = None
    LN = ["F", "B"]
    steps = 0
    while openq:
        f, gcur, node, prev = heapq.heappop(openq)
        if node in came:
            continue
        came[node] = prev
        ix, iy, il = node
        if tgt[il][ix-x0i, iy-y0i] and not lmask[il][ix-x0i, iy-y0i]:
            goal = node
            break
        steps += 1
        if steps > 2500000:
            break
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx_, ny_ = ix+dx, iy+dy
            if not (x0i <= nx_ <= x1i and y0i <= ny_ <= y1i):
                continue
            nb = (nx_, ny_, il)
            if nb in came:
                continue
            if lmask[il][nx_-x0i, ny_-y0i] and not tgt[il][nx_-x0i, ny_-y0i]:
                continue
            ng = gcur + 1
            if ng < gsc.get(nb, 1e18):
                gsc[nb] = ng
                heapq.heappush(openq, (ng+h(nb), ng, nb, node))
        nb = (ix, iy, 1-il)
        if nb not in came and not bV[ix-x0i, iy-y0i]:
            ng = gcur + 40
            if ng < gsc.get(nb, 1e18):
                gsc[nb] = ng
                heapq.heappush(openq, (ng+h(nb), ng, nb, node))
    if goal is None:
        raise RuntimeError(f"heal failed for {net}")
    path = []
    n = goal
    while n is not None:
        path.append(n)
        n = came[n]
    path.reverse()
    LNn = ["F", "B"]
    i = 0
    while i < len(path)-1:
        if path[i+1][2] != path[i][2]:
            add_via(*coord(path[i][0], path[i][1]), net)
            i += 1
            continue
        j = i
        dx = path[i+1][0]-path[i][0]; dy = path[i+1][1]-path[i][1]
        while (j+1 < len(path) and path[j+1][2] == path[i][2]
               and path[j+1][0]-path[j][0] == dx and path[j+1][1]-path[j][1] == dy):
            j += 1
        a = coord(path[i][0], path[i][1]); b = coord(path[j][0], path[j][1])
        add_seg(LNn[path[i][2]], a[0], a[1], b[0], b[1], net)
        i = j

def heal_all():
    from shapely.ops import nearest_points
    nets = set(sg[6] for sg in segs_out) | {v[2] for v in vias_out}
    nets.discard("GND")
    # nets that touch U6 (CYW43439) can never form a single connected
    # component -- the BGA-side hop is a deliberate stub, not a bug.
    u6_nets = {"BT_REG_ON", "BT_DEV_WAKE", "BT_UART_RXD", "BT_UART_TXD",
               "BT_UART_RTS_N", "BT_UART_CTS_N", "BT_HOST_WAKE",
               "CYW_SR_VLX", "CYW_VOUT_CLDO", "CYW_VOUT_LNLDO",
               "CYW_VOUT_3P3", "CYW_PA_VDD", "CYW_VDD1P5",
               "CYW_XTAL_VDD1P2", "CYW_BT_VCO_VDD", "CYW_BTFM_PLL_VDD",
               "CYW_BT_IF_VDD", "CYW_XTAL_XOP", "CYW_XTAL_XON",
               "WLRF_ANT", "WLRF_ANT_MID"}
    def in_u6_bbox(idxs_):
        return all(U6_BBOX[0] <= items[i][2] <= U6_BBOX[2] and
                   U6_BBOX[1] <= items[i][3] <= U6_BBOX[3]
                   for i in idxs_ if items[i][0] != "hole")
    for net in sorted(n for n in nets if n and n not in u6_nets):
        try:
            for attempt in range(8):
                comps, idxs, geoms = net_components(net)
                comps.sort(key=lambda c: -len(c[0]))
                # a mixed net (mostly routable, but with one pad on U6) can
                # have a component that's entirely U6 pins -- e.g. +3V3's
                # U6.F6 ball -- which is exactly as permanent a stub as the
                # whole-net U6 exemption above, just scoped to one pad
                # instead of one net. Don't try to heal those; if nothing
                # else is split, we're done.
                healable = [c for c in comps[1:] if not in_u6_bbox(c[1])]
                if not healable:
                    break
                other = healable[0]
                main_items = [items[i] for i in comps[0][1]]
                other_items = [items[i] for i in other[1]]
                from shapely.ops import unary_union
                gm = unary_union(comps[0][2]); go = unary_union(other[2])
                pa, pb = nearest_points(go, gm)
                print(f"  heal {net}: {len(comps)} comps, gap "
                      f"{go.distance(gm):.2f}mm at ({pa.x:.1f},{pa.y:.1f})")
                astar_heal(net, other_items, main_items,
                           (pa.x, pa.y), (pb.x, pb.y))
        except RuntimeError as e:
            heal_failed.append((net, str(e)))
            print(f"  HEAL FAILED for {net}: {e}")
            continue
        comps, _, _ = net_components(net)
        non_u6 = [c for c in comps if not in_u6_bbox(c[1])]
        if len(non_u6) > 1:
            heal_failed.append((net, f"still split into {len(non_u6)} non-U6 components after 8 heal attempts"))
            print(f"  WARNING: {net} still split into {len(non_u6)} non-U6 components")

if __name__ == "__main__":
    run_routes()
    heal_all()
    stitch_gnd()
    emit()

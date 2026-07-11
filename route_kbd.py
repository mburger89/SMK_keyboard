#!/usr/bin/env python3
"""Route the keyboard PCB.

1. Parse pads/holes from the generated .kicad_pcb (authoritative geometry).
2. Pre-route the key matrix deterministically:
   - diode anode -> socket pad stub (B.Cu)
   - row trunks on B.Cu at y_key-3.6 through every diode cathode
   - column trunks on F.Cu at x_key+6.475 with a via per key
3. A* router (0.2 mm grid, both layers, exact clearance obstacles) for the
   MCU fanout, USB, charger, LDO, buttons, battery-sense nets.
4. GND stitching vias next to SMD GND pads (planes carry GND).
5. Emit tracks.sexp; generate_kbd.py injects it into the board.

Clearance target: 0.2 mm copper-copper, 0.3 mm hole-copper, 0.45 mm edge.
"""
import math, heapq, sys, os
import numpy as np
import sexpdata
from sexpdata import Symbol

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import importlib.util
spec = importlib.util.spec_from_file_location("gen", os.path.join(HERE, "generate_kbd.py"))
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)
NETI, KEYS, key_pos, BOARD = gen.NETI, gen.KEYS, gen.key_pos, gen.BOARD

CL = 0.2          # copper-copper clearance
CLH = 0.3         # hole-copper clearance
W_SIG = 0.25
W_PWR = 0.3
VIA_R = 0.3       # via outer radius
VIA_DRILL = 0.3
STEP = 0.2

PWR_NETS = {"VBUS", "VSYS", "BAT+", "+3V3", "GND"}

def width_for(net):
    return W_PWR if net in PWR_NETS else W_SIG

# ---------------------------------------------------------------- items ----
# item kinds: ('rect', layers, cx, cy, hw, hh, net) axis-aligned half-dims
#             ('circ', layers, cx, cy, r, net)         layers: 'F','B','*'
#             ('hole', '*', cx, cy, r, None)           NPTH / drill
#             ('seg', layer, x1,y1,x2,y2, hw, net)
#             ('via', '*', cx, cy, VIA_R, net)
items = []

def kids(n, name):
    return [x for x in n if isinstance(x, list) and x and x[0] == Symbol(name)]
def kid(n, name):
    k = kids(n, name)
    return k[0] if k else None

def rot_pt(px, py, deg):
    t = math.radians(deg)
    return (px*math.cos(t) + py*math.sin(t), -px*math.sin(t) + py*math.cos(t))

pcb = sexpdata.loads(open(os.path.join(HERE, "gateron_lp_kbd/gateron_lp_kbd.kicad_pcb")).read())
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
        # effective rotation of pad rect
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

# antenna keepout (copper forbidden both layers)
ANT = (148.15, BOARD["y1"], 161.35, 28.2)

segs_out = []   # (layer, x1,y1,x2,y2, w, net)
vias_out = []   # (x, y, net)

def add_seg(layer, x1, y1, x2, y2, net, w=None):
    w = w or width_for(net)
    segs_out.append((layer, x1, y1, x2, y2, w, net))
    items.append(("seg", layer, x1, y1, x2, y2, w/2, net))

def add_via(x, y, net):
    vias_out.append((x, y, net))
    items.append(("via", "*", x, y, VIA_R, net))
    items.append(("hole", "*", x, y, VIA_DRILL/2, net))

# ============================================ 1. matrix pre-route ==========
COLX = {}   # col -> trunk x
for c in range(12):
    COLX[c] = 50.0 + c*19.05 + 6.475
ROWY = {r: 50.0 + r*19.05 - 3.6 for r in range(5)}

for (r, c, u2) in KEYS:
    x, y = key_pos(r, c, u2)
    knet = f"N_R{r}C{c}"
    # diode A pad (x-8.5, y+2.635) -> socket pad1 (x-8.275, y+4.7)
    add_seg("B", x-8.5, y+2.635, x-8.275, y+4.7, knet, W_SIG)
    # diode K (x-8.5, y-0.635) -> row trunk level
    add_seg("B", x-8.5, y-0.635, x-8.5, ROWY[r], f"ROW{r}", W_SIG)
    # socket pad2 -> via (col net)
    add_seg("B", x+6.475, y+5.75, x+6.475, y+8.4, f"COL{c}", W_SIG)
    add_via(x+6.475, y+8.4, f"COL{c}")

# row trunks: connect consecutive key stubs
for r in range(5):
    xs = sorted(key_pos(rr, cc, uu)[0] for (rr, cc, uu) in KEYS if rr == r)
    pts = [x-8.5 for x in xs]
    for a, b in zip(pts, pts[1:]):
        add_seg("B", a, ROWY[r], b, ROWY[r], f"ROW{r}", W_SIG)

# column trunks on F.Cu: from y=45.0 down to lowest key via of that column
for c in range(12):
    rows_c = [r for (r, cc, u2) in KEYS if cc == c]
    ylo = 50.0 + max(rows_c)*19.05 + 8.4
    xt = COLX[c]
    if c == 5:
        # rows 0-3 at x=151.725; row4 (2U) via is at 154.775+6.475=161.25
        add_seg("F", xt, 45.0, xt, 50.0 + 3*19.05 + 8.4, "COL5", W_SIG)
        add_seg("F", xt, 50.0 + 3*19.05 + 8.4, xt, 119.0, "COL5", W_SIG)
        add_seg("F", xt, 119.0, 161.25, 119.0, "COL5", W_SIG)
        add_seg("F", 161.25, 119.0, 161.25, 50.0 + 4*19.05 + 8.4, "COL5", W_SIG)
    elif c == 6:
        add_seg("F", xt, 45.0, xt, 50.0 + 3*19.05 + 8.4, "COL6", W_SIG)  # no row4 key
    else:
        add_seg("F", xt, 45.0, xt, ylo, f"COL{c}", W_SIG)

PRE_ROUTE_SEGS = len(segs_out)
PRE_ROUTE_VIAS = len(vias_out)

# ============================================ 2. A* router =================
X0, Y0 = BOARD["x1"], BOARD["y1"]
NX = int((BOARD["x2"]-X0)/STEP) + 1
NY = int((BOARD["y2"]-Y0)/STEP) + 1

def cell(x, y):
    return (round((x-X0)/STEP), round((y-Y0)/STEP))
def coord(ix, iy):
    return (X0 + ix*STEP, Y0 + iy*STEP)

def raster(mask, it, expand, x0i, y0i, x1i, y1i):
    """mark blocked cells of region slice for item expanded by `expand`"""
    kind = it[0]
    if kind == "rect":
        _, _, cx, cy, hw, hh, _ = it
        xa, xb = cx-hw-expand, cx+hw+expand
        ya, yb = cy-hh-expand, cy+hh+expand
    elif kind in ("circ", "hole", "via"):
        _, _, cx, cy, r = it[:5]
        xa, xb = cx-r-expand, cx+r+expand
        ya, yb = cy-r-expand, cy+r+expand
    else:  # seg
        _, _, x1, y1, x2, y2, hw, _ = it
        xa, xb = min(x1, x2)-hw-expand, max(x1, x2)+hw+expand
        ya, yb = min(y1, y2)-hw-expand, max(y1, y2)+hw+expand
    # block a cell only if its CENTER lies inside the expanded region
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
    """blocked masks for track of halfwidth hw of `net`, plus via mask"""
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
                # foreign or non-plated hole: keep copper away
                e_t = CLH + hw
                raster(bF, ("circ", "*", it[2], it[3], it[4]), e_t, *region)
                raster(bB, ("circ", "*", it[2], it[3], it[4]), e_t, *region)
            # holes always exclude new via barrels (drill-to-drill spacing)
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
        else:
            # same net: still cannot place a via through an SMD pad of a
            # different layer? allowed. no blocking.
            pass
    # antenna keepout + edge margin
    ant = ("rect", "*", (ANT[0]+ANT[2])/2, (ANT[1]+ANT[3])/2,
           (ANT[2]-ANT[0])/2, (ANT[3]-ANT[1])/2, None)
    for m, e in ((bF, hw), (bB, hw), (bV, VIA_R)):
        raster(m, ant, e, *region)
    # board edge: block outside inset
    inset = 0.45
    for m, e in ((bF, hw), (bB, hw), (bV, VIA_R)):
        exi = int(math.ceil((inset+e-STEP*0.001)/STEP))
        # left/right/top/bottom bands relative to region
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
    bV |= bF | bB   # via needs both layers OK at via size... conservative
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
    # free the start/target cells (they sit on same-net pads)
    def rel(c):
        return (c[0]-x0i, c[1]-y0i)
    for cc in (s, t):
        rc = rel(cc)
        if not (0 <= rc[0] < bF.shape[0] and 0 <= rc[1] < bF.shape[1]):
            raise RuntimeError(f"{net}: endpoint outside region")
    start = (s[0], s[1], sl)
    goal = (t[0], t[1], tl)
    # multi-source: any free cell sitting on copper this net has already
    # routed in the A* phase (it is one connected blob per net)
    srcF = np.zeros(bF.shape, bool)
    srcB = np.zeros(bF.shape, bool)
    # sources: only copper in the connected component that contains p1
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
        if it_count > 900000:
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
        # via
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
    # reconstruct
    path = []
    n = goal
    while n is not None:
        path.append(n)
        n = came[n]
    path.reverse()
    # convert to segments + vias
    out_end_first = coord(path[0][0], path[0][1])
    out_end_last = coord(path[-1][0], path[-1][1])
    # connector stubs to exact endpoints
    started_at_p1 = (path[0][0], path[0][1]) == (s[0], s[1])
    if started_at_p1 and (abs(out_end_first[0]-p1[0]) > 1e-6 or abs(out_end_first[1]-p1[1]) > 1e-6):
        add_seg(l1, p1[0], p1[1], out_end_first[0], out_end_first[1], net)
    runs = []
    i = 0
    while i < len(path)-1:
        j = i
        if path[i+1][2] != path[i][2]:
            add_via(*coord(path[i][0], path[i][1]), net)
            i += 1
            continue
        # straight run
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
    """pts: list of ((x,y), layer). route consecutive pairs"""
    for (a, la), (b, lb) in zip(pts, pts[1:]):
        last = None
        for m in (margin, margin+8, margin+18, 42):
            try:
                astar(net, a, la, b, lb, m)
                last = None
                break
            except RuntimeError as e:
                last = e
        if last:
            raise last
        print(f"  routed {net}: {a} -> {b}")

def run_routes():
    # ---- reserved escape stubs for every used module pad ----
    # bottom row pads: straight down; right column: east; left column: west
    bottom = {"12": "ROW0", "13": "ROW1", "15": "COL0", "16": "COL1",
              "17": "USB_DM", "18": "USB_DP", "19": "COL3", "20": "COL4",
              "22": "COL2", "23": "BOOT", "24": "COL5"}
    for num, net in bottom.items():
        x, y, _ = pad_pos[("U1", num)]
        add_seg("F", x, y, x, 39.8, net, W_SIG)
    right = {"25": "COL6", "26": "COL7", "27": "COL8", "28": "COL9",
             "29": "COL10", "30": "COL11"}
    for num, net in right.items():
        x, y, _ = pad_pos[("U1", num)]
        add_seg("F", x, y, 161.8, y, net, W_SIG)
    left = {"3": "+3V3", "5": "ROW2", "6": "ROW3", "8": "EN",
            "9": "VBAT_SENSE", "10": "ROW4"}
    for num, net in left.items():
        x, y, _ = pad_pos[("U1", num)]
        add_seg("F", x, y, 147.6, y, net, W_SIG)

    # ---- deterministic row fanout ----
    # ROW0/ROW1 drop straight from their bottom-row stubs to the trunks
    add_seg("F", 149.95, 39.8, 149.95, ROWY[0], "ROW0", W_SIG)
    add_via(149.95, ROWY[0], "ROW0")
    add_seg("F", 150.75, 39.8, 150.75, ROWY[1], "ROW1", W_SIG)
    add_via(150.75, ROWY[1], "ROW1")
    # ROW2/3/4: exit west, nest down, then run south through the hole-free
    # window between the col4 and col5 switch drill zones (x 130.7..138.9)
    for net, py, dx_, jy, vx in (
            ("ROW2", 32.9, 146.3, 37.6, 137.3),
            ("ROW3", 33.7, 146.9, 38.2, 138.0),
            ("ROW4", 36.9, 147.5, 38.8, 138.7)):
        r = int(net[3])
        add_seg("F", 147.6, py, dx_, py, net, W_SIG)
        add_seg("F", dx_, py, dx_, jy, net, W_SIG)
        add_seg("F", dx_, jy, vx, jy, net, W_SIG)
        add_seg("F", vx, jy, vx, ROWY[r], net, W_SIG)
        add_via(vx, ROWY[r], net)
    # ---- deterministic column fanout ----
    # bottom-row pads: F drop -> via -> B lane -> via -> F drop to trunk top
    bot_cols = {0: (152.35, 41.7), 1: (153.15, 42.34), 2: (157.95, 42.98),
                3: (155.55, 43.62), 4: (156.35, 44.26), 5: (159.55, 44.9)}
    for c, (px, lane) in bot_cols.items():
        net = f"COL{c}"
        add_seg("F", px, 39.8, px, lane, net, W_SIG)
        add_via(px, lane, net)
        add_seg("B", px, lane, COLX[c], lane, net, W_SIG)
        add_via(COLX[c], lane, net)
        add_seg("F", COLX[c], lane, COLX[c], 45.0, net, W_SIG)
    # right-column pads: F staircase entirely on the front layer
    right_cols = {6: (162.4, 43.2, 37.7), 7: (163.0, 42.6, 36.9),
                  8: (163.6, 42.0, 36.1), 9: (164.2, 41.4, 35.3),
                  10: (164.8, 40.8, 34.5), 11: (165.4, 40.2, 33.7)}
    for c, (tx, lane, py) in right_cols.items():
        net = f"COL{c}"
        add_seg("F", 161.8, py, tx, py, net, W_SIG)
        add_seg("F", tx, py, tx, lane, net, W_SIG)
        add_seg("F", tx, lane, COLX[c], lane, net, W_SIG)
        add_seg("F", COLX[c], lane, COLX[c], 45.0, net, W_SIG)

    USBX = 262.0   # USB-C connector x position
    # ---- USB pad-pair ties (manual, interleaved pads) ----
    # D+ : A6 (200.25) + B6 (199.25) tie below pads at y 30.9
    for x in (USBX+0.25, USBX-0.75):
        add_seg("F", x, 29.645, x, 30.9, "USB_DP", W_SIG)
    add_seg("F", USBX-0.75, 30.9, USBX+0.25, 30.9, "USB_DP", W_SIG)
    # D- : B7 (200.75) + A7 (199.75) tie above pads at y 28.2
    for x in (USBX+0.75, USBX-0.25):
        add_seg("F", x, 29.645, x, 28.2, "USB_DM", W_SIG)
    add_seg("F", USBX-0.25, 28.2, USBX+0.75, 28.2, "USB_DM", W_SIG)
    # CC escape stubs (channel too narrow for the grid, exact clearance 0.225)
    add_seg("F", USBX+1.25, 29.645, USBX+1.25, 31.7, "CC1", W_SIG)
    add_seg("F", USBX-1.75, 29.645, USBX-1.75, 32.2, "CC2", W_SIG)
    add_via(USBX-1.75, 32.2, "CC2")     # dive to the empty back layer
    # VBUS tie bar between the two connector VBUS pad pairs (manual, fixed)
    add_seg("F", USBX+2.45, 30.37, USBX+2.45, 33.0, "VBUS")
    add_seg("F", USBX-2.45, 30.37, USBX-2.45, 33.0, "VBUS")
    add_seg("F", USBX-2.45, 33.0, USBX+2.45, 33.0, "VBUS")
    # bring D- down past the pad row on the right of all four
    add_seg("F", 200.75, 28.2, 201.75+0.0, 28.2, "USB_DM", W_SIG) if False else None

    # ---- chains (most constrained first) ----
    # USB data to ESD chip and module
    add_seg("F", *pad_pos[("U4","4")][:2], *pad_pos[("U4","3")][:2], "USB_DP", W_SIG)
    add_seg("F", *pad_pos[("U4","6")][:2], *pad_pos[("U4","1")][:2], "USB_DM", W_SIG)
    route_chain("USB_DM", [((USBX+0.75, 28.2), "F"), pp("U4", "6")], 12)
    route_chain("USB_DP", [((USBX-0.75, 30.9), "F"), pp("U4", "4")], 12)
    # VBUS branch to the ESD chip (tie bar is manual, above)
    route_chain("VBUS", [pp("J1", "A4"), pp("U4", "5")], 14)
    # CC resistors early, before east-side power fills the area
    route_chain("CC1", [((USBX+1.25, 31.7), "F"), pp("R1", "1")], 8)
    route_chain("CC2", [((USBX-1.75, 32.2), "B"), pp("R2", "1")], 8)
    # USB data on to the module
    route_chain("USB_DM", [pp("U4", "1"), pp("U1", "17")], 26)
    route_chain("USB_DP", [pp("U4", "3"), pp("U1", "18")], 26)
    # remaining VBUS branches
    route_chain("VBUS", [pp("U4", "5"), pp("Q1", "1")], 20)
    route_chain("VBUS", [pp("Q1", "1"), pp("D60", "2")], 8)
    route_chain("VBUS", [pp("J1", "B4"), pp("U2", "4")], 10)
    route_chain("VBUS", [pp("U2", "4"), pp("C1", "1")], 8)
    route_chain("VBUS", [pp("U2", "4"), pp("R4", "1")], 8)
    # charger
    route_chain("STAT", [pp("U2", "1"), pp("LED1", "1")], 8)
    route_chain("LED_A", [pp("R4", "2"), pp("LED1", "2")], 6)
    route_chain("PROG", [pp("U2", "5"), pp("R3", "1")], 6)
    # battery rail
    route_chain("BAT+", [pp("J2", "1"), pp("Q1", "2")], 10)
    route_chain("BAT+", [pp("J2", "1"), pp("R6", "1")], 10)
    route_chain("BAT+", [pp("Q1", "2"), pp("U2", "3")], 16)
    route_chain("BAT+", [pp("U2", "3"), pp("C2", "1")], 8)
    # VSYS
    route_chain("VSYS", [pp("Q1", "3"), pp("D60", "1")], 8)
    route_chain("VSYS", [pp("Q1", "3"), pp("U3", "1")], 12)
    route_chain("VSYS", [pp("U3", "1"), pp("C3", "1")], 8)
    route_chain("VSYS", [pp("U3", "1"), pp("SW62", "1")], 14)
    # EN_LDO
    route_chain("EN_LDO", [pp("U3", "3"), pp("R5", "1")], 12)
    route_chain("EN_LDO", [pp("R5", "1"), pp("SW62", "2")], 8)
    # 3V3
    route_chain("+3V3", [pp("U3", "5"), pp("C4", "1")], 8)
    route_chain("+3V3", [pp("C4", "1"), pp("C7", "1")], 12)
    route_chain("+3V3", [pp("C7", "1"), pp("C8", "1")], 6)
    route_chain("+3V3", [pp("C8", "1"), pp("U1", "3")], 8)
    route_chain("+3V3", [pp("R8", "1"), pp("C4", "1")], 12)
    # battery sense
    route_chain("VBAT_SENSE", [pp("U1", "9"), pp("C5", "1")], 10)
    route_chain("VBAT_SENSE", [pp("C5", "1"), pp("R7", "1")], 6)
    route_chain("VBAT_SENSE", [pp("R7", "1"), pp("R6", "2")], 6)
    # EN / BOOT
    route_chain("EN", [pp("U1", "8"), pp("C6", "1")], 8)
    route_chain("EN", [pp("C6", "1"), pp("R8", "2")], 8)
    route_chain("EN", [pp("R8", "2"), pp("SW60", "1")], 26)
    route_chain("BOOT", [pp("U1", "23"), pp("SW61", "1")], 14)

def stitch_gnd():
    """place a GND via + stub next to SMD GND pads (planes carry GND)"""
    import itertools
    gnd_pads = [(ref, num) for (ref, num), (x, y, lay) in pad_pos.items()
                if lay in ("F", "B")]
    count = 0
    for (ref, num), (x, y, lay) in list(pad_pos.items()):
        # find net
        pass
    # collect GND SMD pads from items? use pcb parse again
    for fp in kids(pcb, "footprint"):
        ref = [str(pr[2]) for pr in kids(fp, "property") if str(pr[1]) == "Reference"][0]
        at = kid(fp, "at")
        fx, fy = float(at[1]), float(at[2])
        frot = float(at[3]) if len(at) > 3 else 0
        for p in kids(fp, "pad"):
            if str(p[2]) != "smd":
                continue
            nt = kid(p, "net")
            if not nt or str(nt[2]) != "GND":
                continue
            num = str(p[1])
            if ref == "U1" and num in [str(n) for n in range(36, 49)]:
                continue  # antenna-adjacent row: let the plane take them
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
    """distance between item and a candidate circle/segment >= need?"""
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
            # sample-based conservative check
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
    else:  # seg
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

def emit():
    lines = []
    for i, (layer, x1, y1, x2, y2, w, net) in enumerate(segs_out):
        ln = "F.Cu" if layer == "F" else "B.Cu"
        lines.append(
            f'  (segment (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) '
            f'(width {w:g}) (layer "{ln}") (net {NETI[net]}) (uuid "{gen.NU("rseg", i)}"))')
    for i, (x, y, net) in enumerate(vias_out):
        lines.append(
            f'  (via (at {x:.3f} {y:.3f}) (size {VIA_R*2:g}) (drill {VIA_DRILL:g}) '
            f'(layers "F.Cu" "B.Cu") (net {NETI[net]}) (uuid "{gen.NU("rvia", i)}"))')
    with open(os.path.join(HERE, "tracks.sexp"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"emitted {len(segs_out)} segments, {len(vias_out)} vias")



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
        if steps > 900000:
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
    for net in sorted(n for n in nets if n):
        for attempt in range(8):
            comps, idxs, geoms = net_components(net)
            if len(comps) <= 1:
                break
            comps.sort(key=lambda c: -len(c[0]))
            main_items = [items[i] for i in comps[0][1]]
            other_items = [items[i] for i in comps[1][1]]
            from shapely.ops import unary_union
            gm = unary_union(comps[0][2]); go = unary_union(comps[1][2])
            pa, pb = nearest_points(go, gm)
            print(f"  heal {net}: {len(comps)} comps, gap "
                  f"{go.distance(gm):.2f}mm at ({pa.x:.1f},{pa.y:.1f})")
            astar_heal(net, other_items, main_items,
                       (pa.x, pa.y), (pb.x, pb.y))
        comps, _, _ = net_components(net)
        assert len(comps) == 1, f"{net} still split"

if __name__ == "__main__":
    run_routes()
    heal_all()
    stitch_gnd()
    emit()

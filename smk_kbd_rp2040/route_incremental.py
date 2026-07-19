#!/usr/bin/env python3
"""Incremental HDI router: connects the remaining split nets of the RP2040+CYW43439
board using normal through vias plus F.Cu<->In1.Cu laser microvias (via-in-pad
under the WLBGA-63, 0.4mm pitch).

Approach: per net, find copper islands (geometric touch), build an MST over
islands, A*-route each edge on a 0.1mm 4-layer grid. Existing copper of other
nets is dilated into obstacle masks; same-net copper is free space and acts as
source/target. Emits KiCad 8 segments/vias appended to the .kicad_pcb.

Design rules used (PCBWay HDI 4-layer 1+2+1):
  copper-copper >= 0.127 general, >= 0.10 inside the U6 BGA window
  hole-copper   >= 0.25   hole-hole >= 0.5
  edge          >= 0.45   antenna keepout box: all layers, no new copper
  through via 0.6/0.3, laser microvia F<->In1 0.25/0.1 (in-pad OK)
"""
import math, heapq, sys, re, uuid
import numpy as np
import sexpdata
from sexpdata import Symbol

PCB = "smk_kbd_rp2040.kicad_pcb"
STEP = float(__import__("os").environ.get("STEP","0.1"))
CL = float(__import__("os").environ.get("CL","0.127"))
CL_BGA = 0.10
CLH = 0.25
EDGE = 0.45
VIA_R, VIA_HR = 0.3, 0.15
UVIA_R, UVIA_HR = 0.125, 0.05
LAYERS = ("F", "In1", "In2", "B")
LIDX = {l: i for i, l in enumerate(LAYERS)}
U6_BOX = (42.4, 27.4, 47.6, 32.6)          # BGA window (U6 at 45,30, 13x7 balls 0.4mm)
KEEPOUT = (37.4, 21.9, 64.85, 27.1)          # RM2 RF keepout strip (all layers)
BOARD = (37.5, 22.0, 272.0, 138.5)

def kids(n, name):
    return [x for x in n if isinstance(x, list) and x and x[0] == Symbol(name)]
def kid(n, name):
    k = kids(n, name)
    return k[0] if k else None
def rot_pt(px, py, deg):
    t = math.radians(deg)
    return (px*math.cos(t) + py*math.sin(t), -px*math.sin(t) + py*math.cos(t))
def short_layer(name):
    name = str(name)
    for l in ("In1", "In2"):
        if f"{l}.Cu" in name: return l
    return "B" if "B.Cu" in name else "F"

# ------------------------------------------------------------------ parse ----
pcb = sexpdata.loads(open(PCB).read())
def net_of(node):
    """(net 5 "X") -> "X" ; (net "X") -> "X" ; (net 5) -> id->name ; None -> None"""
    if node is None: return None
    vals = [x for x in node[1:]]
    for v in vals:
        if isinstance(v, str): return v
    return _netbyid.get(int(vals[0])) if vals else None
_netbyid = {}
for n in kids(pcb, "net"):
    try: _netbyid[int(n[1])] = str(n[2])
    except Exception: pass

# items: dicts {kind: circle|capsule|rect, params, layers(set), net(str|None), desc}
items = []
holes = []  # (x, y, r)

for fp in kids(pcb, "footprint"):
    ref = [str(pr[2]) for pr in kids(fp, "property") if str(pr[1]) == "Reference"][0]
    at = kid(fp, "at"); fx, fy = float(at[1]), float(at[2])
    frot = float(at[3]) if len(at) > 3 else 0
    for p in kids(fp, "pad"):
        num = str(p[1]); ptype = str(p[2]); shape = str(p[3])
        pat = kid(p, "at"); px, py = float(pat[1]), float(pat[2])
        prot = float(pat[3]) if len(pat) > 3 else 0
        dx, dy = rot_pt(px, py, frot)
        gx, gy = fx + dx, fy + dy
        sz = kid(p, "size"); sx, sy = float(sz[1]), float(sz[2])
        nt = kid(p, "net"); net = net_of(nt)
        lay = " ".join(str(t) for t in (kid(p, "layers") or []))
        if ptype == "np_thru_hole":
            holes.append((gx, gy, sx/2)); continue
        dr = kid(p, "drill")
        if ptype == "thru_hole":
            lys = set(LAYERS)
            if dr:
                dvals = [float(v) for v in dr[1:] if isinstance(v, (int, float))]
                holes.append((gx, gy, max(dvals)/2 if dvals else 0.5))
        else:
            lys = {short_layer(lay)}
        rot_tot = prot  # pad rot already includes footprint rot in kicad files
        if shape == "circle":
            items.append(dict(kind="circle", x=gx, y=gy, r=sx/2, layers=lys, net=net, desc=f"{ref}.{num}"))
        elif shape == "oval":
            if sx >= sy:
                a, b = rot_pt(-(sx-sy)/2, 0, rot_tot), rot_pt((sx-sy)/2, 0, rot_tot)
                r = sy/2
            else:
                a, b = rot_pt(0, -(sy-sx)/2, rot_tot), rot_pt(0, (sy-sx)/2, rot_tot)
                r = sx/2
            items.append(dict(kind="capsule", x1=gx+a[0], y1=gy+a[1], x2=gx+b[0], y2=gy+b[1], r=r,
                              layers=lys, net=net, desc=f"{ref}.{num}"))
        else:  # rect / roundrect / trapezoid -> rect
            items.append(dict(kind="rect", x=gx, y=gy, w=sx, h=sy, rot=rot_tot,
                              layers=lys, net=net, desc=f"{ref}.{num}"))

for t in kids(pcb, "segment"):
    x1, y1 = float(kid(t, "start")[1]), float(kid(t, "start")[2])
    x2, y2 = float(kid(t, "end")[1]), float(kid(t, "end")[2])
    w = float(kid(t, "width")[1]); lay = short_layer(kid(t, "layer")[1])
    net = net_of(kid(t, "net"))
    items.append(dict(kind="capsule", x1=x1, y1=y1, x2=x2, y2=y2, r=w/2,
                      layers={lay}, net=net, desc="seg"))

for v in kids(pcb, "via"):
    x, y = float(kid(v, "at")[1]), float(kid(v, "at")[2])
    sz = float(kid(v, "size")[1]); dr = float(kid(v, "drill")[1])
    net = net_of(kid(v, "net"))
    vl = kid(v, "layers")
    if vl:
        i1, i2 = sorted((LIDX[short_layer(vl[1])], LIDX[short_layer(vl[2])]))
        lys = set(LAYERS[i1:i2+1])
    else:
        lys = set(LAYERS)
    if len(lys) == 4:
        holes.append((x, y, dr/2))
    items.append(dict(kind="circle", x=x, y=y, r=sz/2, layers=lys, net=net, desc="via"))

# ------------------------------------------------------- geometry helpers ----
def item_dist_grid(it, X, Y):
    """distance from grid points (X,Y meshes) to item copper edge (0 inside)."""
    if it["kind"] == "circle":
        return np.hypot(X - it["x"], Y - it["y"]) - it["r"]
    if it["kind"] == "capsule":
        x1, y1, x2, y2, r = it["x1"], it["y1"], it["x2"], it["y2"], it["r"]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx*dx + dy*dy
        if L2 < 1e-12:
            return np.hypot(X - x1, Y - y1) - r
        tt = np.clip(((X - x1)*dx + (Y - y1)*dy) / L2, 0, 1)
        return np.hypot(X - (x1 + tt*dx), Y - (y1 + tt*dy)) - r
    # rect
    t = math.radians(it["rot"])
    ct, st = math.cos(t), math.sin(t)
    lx = (X - it["x"])*ct - (Y - it["y"])*st
    ly = (X - it["x"])*st + (Y - it["y"])*ct
    qx = np.abs(lx) - it["w"]/2
    qy = np.abs(ly) - it["h"]/2
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0)

def pt_item_dist(it, x, y):
    X = np.array([[x]]); Y = np.array([[y]])
    return float(item_dist_grid(it, X, Y)[0, 0])

def item_bbox(it, m):
    if it["kind"] == "circle":
        return (it["x"]-it["r"]-m, it["y"]-it["r"]-m, it["x"]+it["r"]+m, it["y"]+it["r"]+m)
    if it["kind"] == "capsule":
        return (min(it["x1"], it["x2"])-it["r"]-m, min(it["y1"], it["y2"])-it["r"]-m,
                max(it["x1"], it["x2"])+it["r"]+m, max(it["y1"], it["y2"])+it["r"]+m)
    d = math.hypot(it["w"], it["h"])/2
    return (it["x"]-d-m, it["y"]-d-m, it["x"]+d+m, it["y"]+d+m)

def segseg(g1, g2):
    """min distance between two capsule center-segments minus radii."""
    p = np.array([g1["x1"], g1["y1"]]); q = np.array([g1["x2"], g1["y2"]])
    r = np.array([g2["x1"], g2["y1"]]); s = np.array([g2["x2"], g2["y2"]])
    d1, d2 = q - p, s - r
    # check intersection
    denom = d1[0]*d2[1] - d1[1]*d2[0]
    if abs(denom) > 1e-12:
        t = ((r[0]-p[0])*d2[1] - (r[1]-p[1])*d2[0]) / denom
        u = ((r[0]-p[0])*d1[1] - (r[1]-p[1])*d1[0]) / denom
        if 0 <= t <= 1 and 0 <= u <= 1:
            return -g1["r"] - g2["r"]
    def pt_seg(pt, a, b):
        ab = b - a; L2 = ab.dot(ab)
        if L2 < 1e-12: return float(np.hypot(*(pt-a)))
        tt = max(0.0, min(1.0, (pt-a).dot(ab)/L2))
        return float(np.hypot(*(pt - (a + tt*ab))))
    d = min(pt_seg(p, r, s), pt_seg(q, r, s), pt_seg(r, p, q), pt_seg(s, p, q))
    return d - g1["r"] - g2["r"]

# ------------------------------------------------------------ connectivity ----
def islands_of(net):
    its = [i for i, it in enumerate(items) if it["net"] == net]
    parent = list(range(len(its)))
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    geo = [items[i] for i in its]
    for a in range(len(its)):
        ba = item_bbox(geo[a], 0.02)
        for b in range(a+1, len(its)):
            if not (geo[a]["layers"] & geo[b]["layers"]): continue
            bb = item_bbox(geo[b], 0.02)
            if ba[0] > bb[2] or bb[0] > ba[2] or ba[1] > bb[3] or bb[1] > ba[3]: continue
            # distance between edges
            if geo[a]["kind"] == "circle":
                d = pt_item_dist(geo[b], geo[a]["x"], geo[a]["y"]) - geo[a]["r"]
            elif geo[b]["kind"] == "circle":
                d = pt_item_dist(geo[a], geo[b]["x"], geo[b]["y"]) - geo[b]["r"]
            elif geo[a]["kind"] == "capsule" and geo[b]["kind"] == "capsule":
                d = segseg(geo[a], geo[b])
            else:
                # capsule vs rect (or rect vs rect): sample endpoints/centers
                cands = []
                for g1, g2 in ((geo[a], geo[b]), (geo[b], geo[a])):
                    if g1["kind"] == "capsule":
                        pts = [(g1["x1"], g1["y1"]), (g1["x2"], g1["y2"]),
                               ((g1["x1"]+g1["x2"])/2, (g1["y1"]+g1["y2"])/2)]
                    else:
                        pts = [(g1["x"], g1["y"])]
                    for (px, py) in pts:
                        cands.append(pt_item_dist(g2, px, py) - (g1["r"] if g1["kind"] == "capsule" else 0))
                d = min(cands)
            if d < 0.005:
                ra, rb = find(a), find(b)
                if ra != rb: parent[ra] = rb
    from collections import defaultdict
    comp = defaultdict(list)
    for a in range(len(its)):
        comp[find(a)].append(its[a])
    return list(comp.values())

# ------------------------------------------------------------------- A* ------
def route(net, w, allow_micro=True, region_pad=6.0, max_islands_edges=None, verbose=True):
    """route all islands of `net` together (MST edges). Returns list of emitted elements."""
    emitted = []
    while True:
        comps = islands_of(net)
        if len(comps) <= 1:
            break
        # pick the two closest islands (by item centers, coarse)
        def center(idx_list):
            xs, ys = [], []
            for i in idx_list:
                b = item_bbox(items[i], 0)
                xs.append((b[0]+b[2])/2); ys.append((b[1]+b[3])/2)
            return xs, ys
        best = None
        for a in range(len(comps)):
            xa, ya = center(comps[a])
            for b in range(a+1, len(comps)):
                xb, yb = center(comps[b])
                d = min(math.hypot(x1-x2, y1-y2) for x1, y1 in zip(xa, ya) for x2, y2 in zip(xb, yb))
                if best is None or d < best[0]:
                    best = (d, a, b)
        _, ia, ib = best
        A, B = comps[ia], comps[ib]
        ok = _route_pair(net, A, B, w, allow_micro, region_pad, emitted, verbose)
        if not ok:
            print(f"  !! FAILED to route {net}")
            return emitted, False
    return emitted, True

def _route_pair(net, A, B, w, allow_micro, region_pad, emitted, verbose):
    # region: bbox around the closest pair of items between the two islands
    # (full-island bbox explodes for huge nets like +3V3/VSYS)
    best = None
    for i in A:
        bi = item_bbox(items[i], 0)
        ci = ((bi[0]+bi[2])/2, (bi[1]+bi[3])/2)
        for j in B:
            bj = item_bbox(items[j], 0)
            cj = ((bj[0]+bj[2])/2, (bj[1]+bj[3])/2)
            d = math.hypot(ci[0]-cj[0], ci[1]-cj[1])
            if best is None or d < best[0]:
                best = (d, bi, bj)
    _, bi, bj = best
    bb = (min(bi[0], bj[0]), min(bi[1], bj[1]), max(bi[2], bj[2]), max(bi[3], bj[3]))

    # micro-gap (< 0.35mm): bridge directly with one short segment between
    # the closest anchor points; the A* grid cannot resolve these.
    def anchors(idx):
        it = items[idx]
        if it["kind"] == "circle": return [(it["x"], it["y"])]
        if it["kind"] == "capsule": return [(it["x1"], it["y1"]), (it["x2"], it["y2"])]
        return [(it["x"], it["y"])]
    bridge = None
    for i in A:
        for (ax, ay) in anchors(i):
            for j in B:
                d = pt_item_dist(items[j], ax, ay)
                for (bx, by) in anchors(j):
                    dd = math.hypot(ax-bx, ay-by)
                    if dd < 0.6 and (bridge is None or dd < bridge[0]):
                        la = items[i]["layers"] & items[j]["layers"]
                        if la:
                            bridge = (dd, (ax, ay), (bx, by), sorted(la)[0])
    if bridge is not None and bridge[0] < 0.6:
        _, a, b, lay = bridge
        items.append(dict(kind="capsule", x1=a[0], y1=a[1], x2=b[0], y2=b[1], r=w/2, layers={lay}, net=net, desc="seg"))
        emitted.append(f'\t(segment (start {round(a[0],3)} {round(a[1],3)}) (end {round(b[0],3)} {round(b[1],3)}) (width {w}) (layer "{lay}.Cu") (net "{net}") (uuid "{uuid.uuid4()}"))')
        if verbose: print(f"    bridged micro-gap {bridge[0]:.3f}mm on {lay}")
        return True
    x0 = max(BOARD[0], bb[0] - region_pad); y0 = max(BOARD[1], bb[1] - region_pad)
    x1 = min(BOARD[2], bb[2] + region_pad); y1 = min(BOARD[3], bb[3] + region_pad)
    # snap origin to the 0.1mm lattice so 0.4mm-pitch BGA ball centers land on cells
    x0 = math.floor(x0*10)/10; y0 = math.floor(y0*10)/10
    nx = int((x1 - x0)/STEP) + 1; ny = int((y1 - y0)/STEP) + 1
    if verbose:
        print(f"  routing {net}: region ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f}) grid {nx}x{ny}")
    xs = x0 + np.arange(nx)*STEP
    ys = y0 + np.arange(ny)*STEP
    X, Y = np.meshgrid(xs, ys)  # [ny, nx]

    inb = (X >= U6_BOX[0]) & (X <= U6_BOX[2]) & (Y >= U6_BOX[1]) & (Y <= U6_BOX[3])
    cl_grid = np.where(inb, CL_BGA, CL)

    blocked = np.zeros((4, ny, nx), dtype=bool)
    # board edge & keepout
    edge = (X < BOARD[0]+EDGE+w/2) | (X > BOARD[2]-EDGE-w/2) | (Y < BOARD[1]+EDGE+w/2) | (Y > BOARD[3]-EDGE-w/2)
    keep = (X >= KEEPOUT[0]) & (X <= KEEPOUT[2]) & (Y >= KEEPOUT[1]) & (Y <= KEEPOUT[3])
    for L in range(4):
        blocked[L] |= edge | keep

    via_thru_bad = edge | keep | inb   # NO through vias inside the BGA window, ever
    via_micro_bad = edge | keep

    setA, setB = set(A), set(B)
    for idx, it in enumerate(items):
        b = item_bbox(it, max(CL, CLH) + w/2 + VIA_R + 0.1)
        if b[2] < x0 or b[0] > x1 or b[3] < y0 or b[1] > y1: continue
        ix0 = max(0, int((b[0]-x0)/STEP)); ix1 = min(nx-1, int((b[2]-x0)/STEP)+1)
        iy0 = max(0, int((b[1]-y0)/STEP)); iy1 = min(ny-1, int((b[3]-y0)/STEP)+1)
        sl = (slice(iy0, iy1+1), slice(ix0, ix1+1))
        d = item_dist_grid(it, X[sl], Y[sl])
        if it["net"] == net:
            continue  # same net never blocks
        # copper clearance per layer (+0.02 margin against grid quantization)
        for L, lname in enumerate(LAYERS):
            if lname in it["layers"]:
                blocked[L][sl] |= d < (w/2 + cl_grid[sl] + 0.02)
        # via placement: through via ring must clear foreign copper on every layer it exists
        via_thru_bad[sl] |= d < (VIA_R + cl_grid[sl] + 0.02)
        if it["layers"] & {"F", "In1"}:
            via_micro_bad[sl] |= d < (UVIA_R + cl_grid[sl] + 0.02)
    for (hx, hy, hr) in holes:
        b = (hx-hr-1.0, hy-hr-1.0, hx+hr+1.0, hy+hr+1.0)
        if b[2] < x0 or b[0] > x1 or b[3] < y0 or b[1] > y1: continue
        ix0 = max(0, int((b[0]-x0)/STEP)); ix1 = min(nx-1, int((b[2]-x0)/STEP)+1)
        iy0 = max(0, int((b[1]-y0)/STEP)); iy1 = min(ny-1, int((b[3]-y0)/STEP)+1)
        sl = (slice(iy0, iy1+1), slice(ix0, ix1+1))
        d = np.hypot(X[sl]-hx, Y[sl]-hy) - hr
        for L in range(4):
            blocked[L][sl] |= d < (w/2 + CLH)
        via_thru_bad[sl] |= d < (VIA_HR + 0.5)      # hole-hole
        via_micro_bad[sl] |= d < (UVIA_HR + 0.4)

    # source / target rasters (same-net copper of each island)
    # m: travel/goal cells (inside copper). deep: cells where a FULL micro-via
    # land (r=UVIA_R) fits inside own copper -- only these get the in-pad
    # exemption, so lands can never stick out toward foreign copper.
    def raster(idxs):
        m = np.zeros((4, ny, nx), dtype=bool)
        deep = np.zeros((ny, nx), dtype=bool)
        for i in idxs:
            it = items[i]
            b = item_bbox(it, 0.01)
            if b[2] < x0 or b[0] > x1 or b[3] < y0 or b[1] > y1: continue
            ix0 = max(0, int((b[0]-x0)/STEP)); ix1 = min(nx-1, int((b[2]-x0)/STEP)+1)
            iy0 = max(0, int((b[1]-y0)/STEP)); iy1 = min(ny-1, int((b[3]-y0)/STEP)+1)
            sl = (slice(iy0, iy1+1), slice(ix0, ix1+1))
            d = item_dist_grid(it, X[sl], Y[sl])
            for L, lname in enumerate(LAYERS):
                if lname in it["layers"]:
                    # allow cells slightly outside thin pads: the track (w/2)
                    # still overlaps the pad copper by >= 0.02
                    m[L][sl] |= d < min(0.03, w/2 - 0.02)
                    if lname == "F":
                        deep[sl] |= d < -(UVIA_R - 0.011)
        return m, deep
    srcm, src_deep = raster(A)
    tgtm, tgt_deep = raster(B)
    inpad_ok = src_deep | tgt_deep
    if not srcm.any() or not tgtm.any():
        print("  !! empty source/target raster"); return False

    tl, tyy, txx = np.where(tgtm)
    tpts = np.stack([txx, tyy], axis=1).astype(float)

    def h(ix, iy):
        d = np.min(np.abs(tpts[:, 0]-ix) + 0.0*tpts[:, 1]) if False else None
    # precompute target center for heuristic
    tcx, tcy = float(txx.mean()), float(tyy.mean())
    tminx, tmaxx = int(txx.min()), int(txx.max())
    tminy, tmaxy = int(tyy.min()), int(tyy.max())
    def heur(ix, iy):
        dx = 0 if tminx <= ix <= tmaxx else min(abs(ix-tminx), abs(ix-tmaxx))
        dy = 0 if tminy <= iy <= tmaxy else min(abs(iy-tminy), abs(iy-tmaxy))
        return math.hypot(dx, dy) * STEP * 1.3  # weighted A*: faster, near-optimal

    INF = float("inf")
    g = np.full((4, ny, nx), INF, dtype=np.float32)
    par = np.full((4, ny, nx), -1, dtype=np.int64)
    openq = []
    sl_, sy_, sx_ = np.where(srcm & ~blocked)
    for L, iy, ix in zip(sl_, sy_, sx_):
        g[L, iy, ix] = 0.0
        heapq.heappush(openq, (heur(ix, iy), int(L), int(iy), int(ix)))
    DIRS = [(1, 0, STEP), (-1, 0, STEP), (0, 1, STEP), (0, -1, STEP),
            (1, 1, STEP*1.4142), (1, -1, STEP*1.4142), (-1, 1, STEP*1.4142), (-1, -1, STEP*1.4142)]
    VIA_COST, UVIA_COST = 1.6, 0.9
    found = None
    pops = 0
    while openq:
        f, L, iy, ix = heapq.heappop(openq)
        gc = g[L, iy, ix]
        if f > gc + heur(ix, iy) + 1e-6: continue
        pops += 1
        if tgtm[L, iy, ix]:
            found = (L, iy, ix); break
        for dx, dy, c in DIRS:
            nx_, ny_ = ix+dx, iy+dy
            if not (0 <= nx_ < nx and 0 <= ny_ < ny): continue
            if blocked[L, ny_, nx_] and not tgtm[L, ny_, nx_] and not srcm[L, ny_, nx_]: continue
            if dx and dy:  # no corner-clipping past blocked orthogonal neighbors
                if (blocked[L, iy, nx_] and not tgtm[L, iy, nx_] and not srcm[L, iy, nx_]) or \
                   (blocked[L, ny_, ix] and not tgtm[L, ny_, ix] and not srcm[L, ny_, ix]):
                    continue
            ng = gc + c
            if ng < g[L, ny_, nx_] - 1e-9:
                g[L, ny_, nx_] = ng
                par[L, ny_, nx_] = ((L*ny + iy)*nx + ix)
                heapq.heappush(openq, (ng + heur(nx_, ny_), L, ny_, nx_))
        # vias
        if not via_thru_bad[iy, ix]:
            okall = all(not blocked[LL, iy, ix] or srcm[LL, iy, ix] or tgtm[LL, iy, ix] for LL in range(4))
            if okall:
                for LL in range(4):
                    if LL == L: continue
                    ng = gc + VIA_COST
                    if ng < g[LL, iy, ix] - 1e-9:
                        g[LL, iy, ix] = ng
                        par[LL, iy, ix] = ((L*ny + iy)*nx + ix)
                        heapq.heappush(openq, (ng + heur(ix, iy), LL, iy, ix))
        if allow_micro and L in (0, 1) and (not via_micro_bad[iy, ix]
                or inpad_ok[iy, ix]):  # in-pad micro only when the land fits inside own copper
            LL = 1 - L
            if (not blocked[LL, iy, ix]) or srcm[LL, iy, ix] or tgtm[LL, iy, ix]:
                ng = gc + UVIA_COST
                if ng < g[LL, iy, ix] - 1e-9:
                    g[LL, iy, ix] = ng
                    par[LL, iy, ix] = ((L*ny + iy)*nx + ix)
                    heapq.heappush(openq, (ng + heur(ix, iy), LL, iy, ix))
    if found is None:
        return False
    # ------- reconstruct
    path = []
    L, iy, ix = found
    while True:
        path.append((L, iy, ix))
        p = par[L, iy, ix]
        if p < 0: break
        ix2 = int(p % nx); iy2 = int((p//nx) % ny); L2 = int(p//(nx*ny))
        L, iy, ix = L2, iy2, ix2
    path.reverse()
    # compress to segments + vias
    def XY(iy, ix): return (round(x0+ix*STEP, 3), round(y0+iy*STEP, 3))
    segs = []; vias = []
    i = 0
    while i < len(path)-1:
        L1, y1_, x1_ = path[i]
        L2, y2_, x2_ = path[i+1]
        if L1 != L2:
            # mirror the A* move legality: F<->In1 with (legal spot OR in-pad
            # exemption) was a micro move and MUST be emitted as micro.
            micro_ok = ({L1, L2} == {0, 1} and allow_micro and
                        (not via_micro_bad[y1_, x1_] or inpad_ok[y1_, x1_]))
            vias.append((XY(y1_, x1_), "micro" if micro_ok else "thru", net))
            i += 1; continue
        j = i+1
        ddx, ddy = x2_-x1_, y2_-y1_
        while j+1 < len(path):
            L3, y3_, x3_ = path[j+1]
            if L3 != L1: break
            if (x3_-path[j][2], y3_-path[j][1]) != (ddx, ddy): break
            j += 1
        segs.append((XY(y1_, x1_), XY(path[j][1], path[j][2]), LAYERS[L1], net))
        i = j
    # register as items + emit
    out = []
    for (a, b, lay, _n) in segs:
        if a == b: continue
        items.append(dict(kind="capsule", x1=a[0], y1=a[1], x2=b[0], y2=b[1], r=w/2, layers={lay}, net=net, desc="seg"))
        out.append(f'\t(segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width {w}) (layer "{lay}.Cu") (net "{net}") (uuid "{uuid.uuid4()}"))')
    for ((vx, vy), kind, _n) in vias:
        if kind == "micro":
            items.append(dict(kind="circle", x=vx, y=vy, r=UVIA_R, layers={"F", "In1"}, net=net, desc="via"))
            out.append(f'\t(via micro (at {vx} {vy}) (size 0.25) (drill 0.1) (layers "F.Cu" "In1.Cu") (net "{net}") (uuid "{uuid.uuid4()}"))')
        else:
            items.append(dict(kind="circle", x=vx, y=vy, r=VIA_R, layers=set(LAYERS), net=net, desc="via"))
            holes.append((vx, vy, VIA_HR))
            out.append(f'\t(via (at {vx} {vy}) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "{net}") (uuid "{uuid.uuid4()}"))')
    emitted.extend(out)
    if verbose:
        print(f"    ok: {len(segs)} segs, {len(vias)} vias ({sum(1 for v in vias if v[1]=='micro')} micro), pops {pops}")
    return True

def via_thru_ok_here(via_thru_bad, iy, ix):
    return not via_thru_bad[iy, ix]

# ------------------------------------------------------------------ main -----
# Most-constrained first: sealed inner balls claim their In1 exits before
# easier nets crowd the field.
PLAN = [
    ("LEDD0_R", 0.2, False),
    ("VSYS", 0.3, False),
    ("+3V3", 0.3, False),
    ("WL_DOUT", 0.15, False),
    ("WL_IRQ", 0.15, False),
    ("WL_CS", 0.15, False),
    ("WL_CLK", 0.15, False),
    ("WL_DATA", 0.15, False),
    ("WL_ON", 0.15, False),
    ("QSPI_SD1", 0.15, False),
    ("QSPI_SD2", 0.15, False),
    # net, width, allow_micro
    ("+3V3", 0.2, False),            # F6, sealed
    ("BT_REG_ON", 0.15, False),      # E6, sealed
    ("BT_UART_CTS_N", 0.15, False),  # B2, sealed
    ("CYW_VOUT_CLDO", 0.2, False),   # C6/D3/G4, G4 sealed
    ("CYW_XTAL_VDD", 0.2, False),    # F2/E2 sealed + rail merge
    ("VSYS", 0.25, False),           # F7 boxed
    ("CYW_PA_VDD", 0.25, False),     # M1 boxed
    ("CYW_VDD1P5", 0.25, False),
    ("BT_UART_RXD", 0.15, False),
    ("BT_UART_TXD", 0.15, False),
    ("BT_UART_RTS_N", 0.15, False),
    ("BT_DEV_WAKE", 0.15, False),
    ("BT_HOST_WAKE", 0.15, False),
    ("CYW_VOUT_LNLDO", 0.25, False),
    ("USB_DM", 0.2, False),
]

if __name__ == "__main__":
    all_out = []
    fails = []
    args = sys.argv[1:]
    if args and args[0] == "--check":
        for net, w, micro in PLAN:
            comps = islands_of(net)
            if len(comps) > 1:
                print(f"{net}: {len(comps)} islands")
        sys.exit(0)
    only = args if args else None
    for net, w, micro in PLAN:
        if only and net not in only: continue
        print(f"== {net}", flush=True)
        out, ok = route(net, w, allow_micro=micro)
        if out:  # persist immediately so partial runs survive
            s = open(PCB).read()
            anchor = s.index("\n\t(zone")
            s = s[:anchor] + "\n" + "\n".join(out) + s[anchor:]
            open(PCB, "w").write(s)
            print(f"  wrote {len(out)} elements", flush=True)
        if not ok: fails.append(net)
    print("FAILED:", fails if fails else "none")

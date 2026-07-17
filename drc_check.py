#!/usr/bin/env python3
"""Independent DRC + connectivity check of the routed board.

Reads the final .kicad_pcb, builds exact shapely geometry for every pad,
track, via and hole, then checks:
  A. copper-copper clearance >= 0.19 mm between different nets (per layer)
  B. hole-copper clearance >= 0.25 mm (non-plated + foreign-net drills)
  C. board-edge clearance >= 0.3 mm
  D. per-net connectivity (every net = one connected component;
     GND allowed islands - the pour connects them)
"""
import math, sys
import sexpdata
from sexpdata import Symbol
from shapely.geometry import Point, LineString, box, Polygon
from shapely.strtree import STRtree
from shapely import affinity

# Board path can be overridden on the command line, e.g.:
#   .routing_venv/bin/python3 drc_check.py gateron_lp_kbd_rp2040/gateron_lp_kbd_rp2040.kicad_pcb
PCB = sys.argv[1] if len(sys.argv) > 1 else "gateron_lp_kbd/gateron_lp_kbd.kicad_pcb"
CL_MIN = 0.19
HOLE_MIN = 0.25
EDGE_MIN = 0.30
# All copper layers checked. The RP2040 variant is a 4-layer board with
# real routing on In1/In2 (row trunks, power/QSPI expressways) -- a
# 2-layer-only check silently skips those tracks for both clearance and
# connectivity. Harmless for the 2-layer ESP32 board (inner groups empty).
LAYERS = ("F", "In1", "In2", "B")

def short_layer(name):
    name = str(name)
    for l in ("In1", "In2"):
        if f"{l}.Cu" in name:
            return l
    return "B" if "B.Cu" in name else "F"

def kids(n, name):
    return [x for x in n if isinstance(x, list) and x and x[0] == Symbol(name)]
def kid(n, name):
    k = kids(n, name)
    return k[0] if k else None

def rot_pt(px, py, deg):
    t = math.radians(deg)
    return (px*math.cos(t) + py*math.sin(t), -px*math.sin(t) + py*math.cos(t))

pcb = sexpdata.loads(open(PCB).read())

copper = []   # (geom, layer 'F'/'B', net, desc)
holes = []    # (Point-geom, net, desc)  net=None for NPTH
BOARD = None
for g in kids(pcb, "gr_rect"):
    if str(kid(g, "layer")[1]) == "Edge.Cuts":
        st, en = kid(g, "start"), kid(g, "end")
        BOARD = (float(st[1]), float(st[2]), float(en[1]), float(en[2]))
netnames = {}
for n in kids(pcb, "net"):
    netnames[int(n[1])] = str(n[2])

for fp in kids(pcb, "footprint"):
    ref = [str(pr[2]) for pr in kids(fp, "property") if str(pr[1]) == "Reference"][0]
    at = kid(fp, "at")
    fx, fy = float(at[1]), float(at[2])
    frot = float(at[3]) if len(at) > 3 else 0
    for p in kids(fp, "pad"):
        num, ptype, shape = str(p[1]), str(p[2]), str(p[3])
        pat = kid(p, "at")
        px, py = float(pat[1]), float(pat[2])
        prot = float(pat[3]) if len(pat) > 3 else 0
        # NOTE: verified empirically (see /tmp/mirror_test2.py-style check
        # against real trace/via endpoint coincidence across 599 back-layer
        # SMD pads) that this generator's back-layer (B.Cu) footprints
        # already store pad-local coordinates in final/placed form -- no
        # extra runtime mirroring is needed or correct here. An earlier
        # attempt to "fix" this by mirroring was itself wrong; left as a
        # note in case this is revisited.
        dx, dy = rot_pt(px, py, frot)
        gx, gy = fx+dx, fy+dy
        sz = kid(p, "size")
        sx, sy = float(sz[1]), float(sz[2])
        nt = kid(p, "net")
        if nt is None:
            net = None
        elif isinstance(nt[1], str):
            net = nt[1]          # (net "NAME") -- no index, as some scripted edits emit
        elif len(nt) > 2:
            net = str(nt[2])     # (net <index> "NAME")
        else:
            net = None
        desc = f"{ref}.{num}"
        if ptype == "np_thru_hole":
            holes.append((Point(gx, gy).buffer(sx/2, 32), None, desc))
            continue
        if abs(prot % 180) == 90:
            sx, sy = sy, sx
        if shape in ("rect", "roundrect"):
            geom = box(gx-sx/2, gy-sy/2, gx+sx/2, gy+sy/2)
        elif shape == "oval":
            if sx > sy:
                geom = LineString([(gx-(sx-sy)/2, gy), (gx+(sx-sy)/2, gy)]).buffer(sy/2, 32)
            else:
                geom = LineString([(gx, gy-(sy-sx)/2), (gx, gy+(sy-sx)/2)]).buffer(sx/2, 32)
        else:
            geom = Point(gx, gy).buffer(max(sx, sy)/2, 32)
        lay = " ".join(str(t) for t in kid(p, "layers"))
        if ptype == "thru_hole":
            for L in LAYERS:
                copper.append((geom, L, net, desc))
            dr = kid(p, "drill")
            if dr:
                vals = [float(v) for v in dr[1:] if not isinstance(v, (Symbol, list))]
                dd = max(vals) if vals else 0
                holes.append((Point(gx, gy).buffer(dd/2, 32), net, desc))
        else:
            copper.append((geom, short_layer(lay), net, desc))

def seg_net(sg):
    # Normally (net <index>) referencing the top (net <index> "<name>")
    # table. Some recently hand/script-added segments (the RGB chain hops)
    # instead store (net "<name>") directly -- tolerate both.
    raw = kid(sg, "net")[1]
    if isinstance(raw, str):
        return raw
    return netnames[int(raw)]

for sg in kids(pcb, "segment"):
    st, en = kid(sg, "start"), kid(sg, "end")
    w = float(kid(sg, "width")[1])
    lay = short_layer(kid(sg, "layer")[1])
    net = seg_net(sg)
    ls = LineString([(float(st[1]), float(st[2])), (float(en[1]), float(en[2]))])
    copper.append((ls.buffer(w/2, 16), lay, net, "track"))

for v in kids(pcb, "via"):
    at = kid(v, "at")
    x, y = float(at[1]), float(at[2])
    sz = float(kid(v, "size")[1])
    dr = float(kid(v, "drill")[1])
    vraw = kid(v, "net")[1]
    net = vraw if isinstance(vraw, str) else netnames[int(vraw)]
    g = Point(x, y).buffer(sz/2, 32)
    for L in LAYERS:
        copper.append((g, L, net, "via"))
    holes.append((Point(x, y).buffer(dr/2, 32), net, "via"))

print(f"copper items: {len(copper)}, holes: {len(holes)}")

# ---------------- A. copper-copper clearance ----------------
viol = 0
for LAY in LAYERS:
    geoms = [c[0] for c in copper if c[1] == LAY]
    meta = [c for c in copper if c[1] == LAY]
    tree = STRtree(geoms)
    import numpy as np
    for i, (g, lay, net, desc) in enumerate(meta):
        idx = tree.query(g.buffer(CL_MIN + 0.01))
        for j in idx:
            j = int(j)
            if j <= i:
                continue
            g2, lay2, net2, desc2 = meta[j]
            if net == net2 and net is not None:
                continue
            d = g.distance(g2)
            if d < CL_MIN:
                print(f"CLEARANCE {LAY}: {desc}({net}) <-> {desc2}({net2}) = {d:.3f}")
                viol += 1
print(f"A. copper clearance violations: {viol}")

# ---------------- B. hole-copper ----------------
hviol = 0
for LAY in LAYERS:
    geoms = [c[0] for c in copper if c[1] == LAY]
    meta = [c for c in copper if c[1] == LAY]
    tree = STRtree(geoms)
    for hg, hnet, hdesc in holes:
        idx = tree.query(hg.buffer(HOLE_MIN + 0.01))
        for j in idx:
            j = int(j)
            g2, lay2, net2, desc2 = meta[j]
            if hnet is not None and net2 == hnet:
                continue
            d = hg.distance(g2)
            if d < HOLE_MIN:
                print(f"HOLE {LAY}: {hdesc}({hnet}) <-> {desc2}({net2}) = {d:.3f}")
                hviol += 1
# hole-to-hole
hgeoms = [h[0] for h in holes]
htree = STRtree(hgeoms)
for i, (hg, hnet, hdesc) in enumerate(holes):
    for j in htree.query(hg.buffer(0.26)):
        j = int(j)
        if j <= i:
            continue
        d = hg.distance(holes[j][0])
        if d < 0.25:
            print(f"HOLE-HOLE: {hdesc} <-> {holes[j][2]} = {d:.3f}")
            hviol += 1
print(f"B. hole clearance violations: {hviol}")

# ---------------- C. edge ----------------
eviol = 0
bx1, by1, bx2, by2 = min(BOARD[0], BOARD[2]), min(BOARD[1], BOARD[3]), max(BOARD[0], BOARD[2]), max(BOARD[1], BOARD[3])
inner = box(bx1+EDGE_MIN, by1+EDGE_MIN, bx2-EDGE_MIN, by2-EDGE_MIN)
for g, lay, net, desc in copper:
    if not inner.contains(g):
        print(f"EDGE: {desc}({net}) layer {lay}")
        eviol += 1
print(f"C. edge violations: {eviol}")

# ---------------- D. connectivity ----------------
parent = {}
def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb

bynet = {}
for i, (g, lay, net, desc) in enumerate(copper):
    parent[i] = i
    bynet.setdefault(net, []).append(i)
# vias connect F and B copies of same object (same geom idx pairs handled below)
for net, idxs in bynet.items():
    if net is None:
        continue
    # group by layer for touching; via/THT items appear on all layers
    for LAY in LAYERS:
        sub = [i for i in idxs if copper[i][1] == LAY]
        geoms = [copper[i][0] for i in sub]
        if not geoms:
            continue
        tree = STRtree(geoms)
        for a_i, i in enumerate(sub):
            for b_i in tree.query(geoms[a_i].buffer(0.001)):
                b_i = int(b_i)
                j = sub[b_i]
                if j > i and copper[i][0].distance(copper[j][0]) < 0.005:
                    union(i, j)
# tie F/B copies of vias and THT pads: same desc+net pairs at same location
from collections import defaultdict
loc = defaultdict(list)
for i, (g, lay, net, desc) in enumerate(copper):
    if desc == "via" or "." in desc:
        c = g.centroid
        loc[(round(c.x, 3), round(c.y, 3), net, desc)].append(i)
for k, idxs in loc.items():
    for a, b in zip(idxs, idxs[1:]):
        union(a, b)

bad = 0
for net, idxs in sorted(bynet.items(), key=lambda kv: str(kv[0])):
    if net is None:
        continue
    comps = {find(i) for i in idxs}
    if len(comps) > 1:
        if net == "GND":
            print(f"D. GND components: {len(comps)} (joined by pour - OK)")
        else:
            print(f"D. NET SPLIT: {net} has {len(comps)} components")
            bad += 1
print(f"D. split nets (excluding GND): {bad}")
total = viol + hviol + eviol + bad
print("TOTAL PROBLEMS:", total)
sys.exit(1 if total else 0)

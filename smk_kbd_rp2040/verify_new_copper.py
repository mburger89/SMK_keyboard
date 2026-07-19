#!/usr/bin/env python3
"""Exact (shapely) verification of the copper added by route_incremental.py.

New items = segments/vias whose uuid is not in the pre-routing backup
(/tmp/pcb.bak) + the FB1 footprint pads. Checks:
  A. copper-copper clearance to foreign nets, per layer (micro-via layer spans
     honored): >= 0.10 inside the U6 BGA window, >= 0.127 elsewhere
  B. through-via holes: >= 0.25 to foreign copper, >= 0.5 to other holes
  C. board edge >= 0.45, antenna keepout: no new copper
  D. micro vias: land centered on BGA ball when in-pad (offset <= 0.06)
"""
import math, re, sys
import sexpdata
from sexpdata import Symbol
from shapely.geometry import Point, LineString, box
from shapely.strtree import STRtree
from shapely import affinity

PCB = "smk_kbd_rp2040.kicad_pcb"
BAK = "/tmp/pcb.bak"
LAYERS = ("F", "In1", "In2", "B")
U6_BOX = box(42.4, 27.4, 47.6, 32.6)
KEEPOUT = box(37.5, 22.0, 64.75, 27.0)
BOARD = box(37.5, 22.0, 272.0, 138.5)
CL, CL_BGA, CLH = 0.127, 0.10, 0.25

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

bak_uuids = set(re.findall(r'\(uuid "([0-9a-f-]+)"\)', open(BAK).read()))
pcb = sexpdata.loads(open(PCB).read())
netname = {}
for n in kids(pcb, "net"):
    try: netname[int(n[1])] = str(n[2])
    except Exception: pass
def net_of(node):
    if node is None: return None
    for v in node[1:]:
        if isinstance(v, str): return v
    return netname.get(int(node[1])) if len(node) > 1 else None

def pad_geom(shape, gx, gy, sx, sy, rot):
    if shape == "circle":
        return Point(gx, gy).buffer(sx/2, 32)
    if shape == "oval":
        if sx >= sy:
            g = LineString([(gx-(sx-sy)/2, gy), (gx+(sx-sy)/2, gy)]).buffer(sy/2, 16)
        else:
            g = LineString([(gx, gy-(sy-sx)/2), (gx, gy+(sy-sx)/2)]).buffer(sx/2, 16)
        return affinity.rotate(g, -rot, origin=(gx, gy))
    g = box(gx-sx/2, gy-sy/2, gx+sx/2, gy+sy/2)
    return affinity.rotate(g, -rot, origin=(gx, gy)) if rot % 180 else g

all_items = []   # (geom, layerset, net, desc, is_new)
holes = []       # (geom(point-buffer), r, desc, is_new)

for fp in kids(pcb, "footprint"):
    ref = [str(pr[2]) for pr in kids(fp, "property") if str(pr[1]) == "Reference"][0]
    at = kid(fp, "at"); fx, fy = float(at[1]), float(at[2])
    frot = float(at[3]) if len(at) > 3 else 0
    for p in kids(fp, "pad"):
        num = str(p[1]); ptype = str(p[2]); shape = str(p[3])
        pat = kid(p, "at"); px, py = float(pat[1]), float(pat[2])
        prot = float(pat[3]) if len(pat) > 3 else 0
        dx, dy = rot_pt(px, py, frot)
        gx, gy = fx+dx, fy+dy
        sz = kid(p, "size"); sx, sy = float(sz[1]), float(sz[2])
        nt = kid(p, "net"); net = net_of(nt)
        lay = " ".join(str(t) for t in (kid(p, "layers") or []))
        if ptype == "np_thru_hole":
            holes.append((Point(gx, gy), sx/2, f"{ref}.{num}", False)); continue
        lys = set(LAYERS) if ptype == "thru_hole" else {short_layer(lay)}
        if ptype == "thru_hole":
            dr = kid(p, "drill")
            dvals = [float(v) for v in dr[1:] if isinstance(v, (int, float))] if dr else []
            holes.append((Point(gx, gy), max(dvals)/2 if dvals else 0.5, f"{ref}.{num}", False))
        g = pad_geom(shape, gx, gy, sx, sy, prot)
        all_items.append((g, lys, net, f"{ref}.{num}", ref in ("R14", "R15", "U6")))

for t in kids(pcb, "segment"):
    u = str(kid(t, "uuid")[1]) if kid(t, "uuid") else ""
    x1, y1 = float(kid(t, "start")[1]), float(kid(t, "start")[2])
    x2, y2 = float(kid(t, "end")[1]), float(kid(t, "end")[2])
    w = float(kid(t, "width")[1]); lay = short_layer(kid(t, "layer")[1])
    net = net_of(kid(t, "net"))
    g = LineString([(x1, y1), (x2, y2)]).buffer(w/2, 16)
    all_items.append((g, {lay}, net, f"seg({x1:.1f},{y1:.1f}-{x2:.1f},{y2:.1f})@{lay}", u not in bak_uuids))

for v in kids(pcb, "via"):
    u = str(kid(v, "uuid")[1]) if kid(v, "uuid") else ""
    x, y = float(kid(v, "at")[1]), float(kid(v, "at")[2])
    sz = float(kid(v, "size")[1]); dr = float(kid(v, "drill")[1])
    net = net_of(kid(v, "net"))
    vl = kid(v, "layers")
    micro = any(str(a) == "micro" for a in v)
    if vl and micro:
        i1, i2 = sorted((LAYERS.index(short_layer(vl[1])), LAYERS.index(short_layer(vl[2]))))
        lys = set(LAYERS[i1:i2+1])
    else:
        lys = set(LAYERS)
        holes.append((Point(x, y), dr/2, f"via({x:.2f},{y:.2f})", u not in bak_uuids))
    all_items.append((Point(x, y).buffer(sz/2, 32), lys, net,
                      f"{'uvia' if micro else 'via'}({x:.2f},{y:.2f})", u not in bak_uuids))

new_idx = [i for i, it in enumerate(all_items) if it[4]]
print(f"total items {len(all_items)}, new {len(new_idx)}, holes {len(holes)}")

problems = 0
# --- A. clearance per layer
for L in LAYERS:
    idxs = [i for i, it in enumerate(all_items) if L in it[1]]
    geoms = [all_items[i][0] for i in idxs]
    tree = STRtree(geoms)
    for i in new_idx:
        g, lys, net, desc, _ = all_items[i]
        if L not in lys: continue
        for jj in tree.query(g.buffer(CL + 0.02)):
            j = idxs[int(jj)]
            if j == i: continue
            g2, lys2, net2, desc2, new2 = all_items[j]
            if net2 == net or net2 is None and desc2.split(".")[0] == desc.split(".")[0]: continue
            if net2 == net: continue
            d = g.distance(g2)
            need = CL_BGA if (U6_BOX.contains(g.centroid) and U6_BOX.contains(g2.centroid)) else CL
            if d < need - 1e-6:
                print(f"CLEARANCE {L}: {desc}({net}) <-> {desc2}({net2}) = {d:.3f} (need {need})")
                problems += 1
# --- B. holes
hole_geoms = [h[0].buffer(h[1], 16) for h in holes]
for i in new_idx:
    g, lys, net, desc, _ = all_items[i]
    for (hp, hr, hdesc, hnew) in holes:
        if hdesc == desc: continue
        d = hp.distance(g.centroid) if False else g.distance(hp) - hr
        if d < CLH - 1e-6 and not (desc.startswith("via") and hdesc == desc):
            # same-net via hole under its own track is fine
            hnet = None
            print(f"HOLE: {desc}({net}) vs hole {hdesc} = {d:.3f}") or None
            problems += 1
for a in range(len(holes)):
    if not holes[a][3]: continue
    for b in range(len(holes)):
        if a == b: continue
        d = holes[a][0].distance(holes[b][0]) - holes[a][1] - holes[b][1]
        if d < 0.5 - 1e-6:
            print(f"HOLE-HOLE: {holes[a][2]} vs {holes[b][2]} = {d:.3f}")
            problems += 1
# --- C. edge & keepout
for i in new_idx:
    g, lys, net, desc, _ = all_items[i]
    if g.distance(BOARD.exterior) < 0.45 - 1e-6 or not BOARD.contains(g.centroid):
        print(f"EDGE: {desc}({net})"); problems += 1
    if g.intersects(KEEPOUT):
        print(f"KEEPOUT: {desc}({net})"); problems += 1
# --- D. micro via centering on balls
balls = {d: it for i, (gg, ll, nn, d, nw) in enumerate(all_items) if d.startswith("U6.") for it, _ in [((gg, nn), 0)]}
for i in new_idx:
    g, lys, net, desc, _ = all_items[i]
    if not desc.startswith("uvia"): continue
    c = g.centroid
    if U6_BOX.contains(c):
        best = None
        for d2, (g2, n2) in balls.items():
            dd = c.distance(g2.centroid)
            if best is None or dd < best[0]: best = (dd, d2, n2)
        if best and best[0] > 0.06 and best[0] < 0.2:
            print(f"UVIA off-center: {desc}({net}) {best[0]:.3f} from {best[1]}({best[2]})")
            problems += 1
print("PROBLEMS:", problems)

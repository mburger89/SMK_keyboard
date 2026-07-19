#!/usr/bin/env python3
"""Report split nets with their copper islands (which pads are in which island,
plus dangling stub endpoints). Geometry-touch connectivity like drc_check.py."""
import math, sys
import sexpdata
from sexpdata import Symbol
from shapely.geometry import Point, LineString, box
from shapely import affinity

PCB = sys.argv[1] if len(sys.argv) > 1 else "smk_kbd_rp2040.kicad_pcb"
LAYERS = ("F", "In1", "In2", "B")

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

pcb = sexpdata.loads(open(PCB).read())
items = []  # (geom, layers_tuple, net, desc)

for fp in kids(pcb, "footprint"):
    ref = [str(pr[2]) for pr in kids(fp, "property") if str(pr[1]) == "Reference"][0]
    at = kid(fp, "at"); fx, fy = float(at[1]), float(at[2])
    frot = float(at[3]) if len(at) > 3 else 0
    for p in kids(fp, "pad"):
        num = str(p[1]); ptype = str(p[2])
        pat = kid(p, "at"); px, py = float(pat[1]), float(pat[2])
        dx, dy = rot_pt(px, py, frot)
        gx, gy = fx+dx, fy+dy
        sz = kid(p, "size"); sx, sy = float(sz[1]), float(sz[2])
        nt = kid(p, "net"); net = str(nt[2]) if nt else None
        if net is None: continue
        lay = " ".join(str(t) for t in (kid(p, "layers") or []))
        if ptype == "thru_hole":
            lys = LAYERS
        else:
            lys = (short_layer(lay),)
        r = max(sx, sy)/2
        items.append((Point(gx, gy).buffer(r, 8), lys, net, f"{ref}.{num}"))

for t in kids(pcb, "segment"):
    x1,y1 = float(kid(t,"start")[1]), float(kid(t,"start")[2])
    x2,y2 = float(kid(t,"end")[1]), float(kid(t,"end")[2])
    w = float(kid(t,"width")[1]); lay = short_layer(kid(t,"layer")[1])
    nid = int(kid(t,"net")[1])
    items.append((LineString([(x1,y1),(x2,y2)]).buffer(w/2, 4), (lay,), nid, f"seg({x1:.1f},{y1:.1f})-({x2:.1f},{y2:.1f})@{lay}"))

for v in kids(pcb, "via"):
    x,y = float(kid(v,"at")[1]), float(kid(v,"at")[2])
    sz = float(kid(v,"size")[1]); nid = int(kid(v,"net")[1])
    vl = kid(v,"layers")
    if vl:
        l1, l2 = short_layer(vl[1]), short_layer(vl[2])
        i1, i2 = sorted((LAYERS.index(l1), LAYERS.index(l2)))
        lys = LAYERS[i1:i2+1]
    else:
        lys = LAYERS
    items.append((Point(x,y).buffer(sz/2, 8), lys, nid, f"via({x:.1f},{y:.1f})"))

# map numeric net ids to names
netname = {}
for n in kids(pcb, "net"):
    netname[int(n[1])] = str(n[2])
norm = []
for g, lys, net, d in items:
    if isinstance(net, int): net = netname.get(net, str(net))
    norm.append((g, lys, net, d))

from collections import defaultdict
bynet = defaultdict(list)
for it in norm:
    bynet[it[2]].append(it)

targets = sys.argv[2:] if len(sys.argv) > 2 else None
for net, its in sorted(bynet.items()):
    if net in (None, "", "GND"): continue
    if targets and net not in targets: continue
    n = len(its)
    parent = list(range(n))
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for i in range(n):
        gi, li, _, _ = its[i]
        for j in range(i+1, n):
            gj, lj, _, _ = its[j]
            if not set(li) & set(lj): continue
            if gi.distance(gj) < 0.005:
                pa, pb = find(i), find(j)
                if pa != pb: parent[pa] = pb
    comps = defaultdict(list)
    for i in range(n):
        comps[find(i)].append(its[i][3])
    if len(comps) > 1:
        print(f"NET {net}: {len(comps)} islands")
        for k, mem in comps.items():
            pads = [m for m in mem if not m.startswith(("seg(", "via("))]
            segs = [m for m in mem if m.startswith(("seg(", "via("))]
            tail = f" +{len(segs)} copper" if segs else ""
            ends = segs[:2] if not pads else []
            print(f"   [{'|'.join(pads) if pads else 'stub'}{tail}] {' '.join(ends)}")

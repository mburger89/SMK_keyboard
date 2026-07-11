#!/usr/bin/env python3
"""Attach 3D models to every footprint (board file + kbd.pretty library).

- Switches:   user-supplied Gateron_KS-33.step (origin at center, z0 = PCB top)
              + generated hot-swap socket model under the board
- Stock parts: models shipped with KiCad 9 (${KICAD9_3DMODEL_DIR}/...)
- ESP32-C6-MINI-1 and MSK-12C02 slide switch: generated VRML models
Per-instance selection in the board file (R/C/LED share one footprint but get
their own model).
"""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.join(HERE, "gateron_lp_kbd")
M3D = os.path.join(PRJ, "3dmodels")
os.makedirs(M3D, exist_ok=True)

S = 1/2.54  # mm -> VRML unit

def wrl_box(cx, cy, cz, sx, sy, sz, rgb):
    return f"""Transform {{
  translation {cx*S:.4f} {cy*S:.4f} {cz*S:.4f}
  children [ Shape {{
    appearance Appearance {{ material Material {{ diffuseColor {rgb} shininess 0.3 }} }}
    geometry Box {{ size {sx*S:.4f} {sy*S:.4f} {sz*S:.4f} }}
  }} ]
}}
"""

def write_wrl(name, boxes):
    with open(os.path.join(M3D, name), "w") as f:
        f.write("#VRML V2.0 utf8\n")
        for b in boxes:
            f.write(b)

# ---- ESP32-C6-MINI-1: PCB + shield can + antenna area ----
write_wrl("esp32_c6_mini1.wrl", [
    wrl_box(0, 0, 0.4, 13.2, 16.6, 0.8, "0.05 0.25 0.12"),      # module PCB
    wrl_box(0, -2.7, 1.55, 12.4, 10.8, 1.5, "0.75 0.76 0.78"),  # shield can
    wrl_box(0, 5.6, 0.88, 10.0, 4.6, 0.16, "0.85 0.7 0.25"),    # antenna area
])

# ---- MSK-12C02 slide switch: body + lever + pins ----
write_wrl("slide_msk12c02.wrl", [
    wrl_box(0, 0.2, 1.75, 8.9, 3.0, 3.5, "0.75 0.76 0.78"),
    wrl_box(-1.8, 2.4, 1.75, 2.2, 1.6, 1.4, "0.15 0.15 0.15"),  # side lever
    wrl_box(0, -1.6, 0.5, 6.5, 0.9, 0.4, "0.85 0.85 0.6"),
])

# ---- Gateron hot-swap socket (under the board, offset handled at insert) ----
write_wrl("gateron_socket.wrl", [
    wrl_box(-0.9, -5.225, -0.925, 11.85, 4.35, 1.85, "0.12 0.12 0.12"),
    wrl_box(-4.4, -4.7, -0.925, 3.4, 3.4, 1.85, "0.12 0.12 0.12"),
    wrl_box(2.6, -5.75, -0.925, 3.4, 3.4, 1.85, "0.12 0.12 0.12"),
    wrl_box(-7.6, -4.7, -0.8, 1.6, 2.2, 0.4, "0.8 0.75 0.5"),   # solder tabs
    wrl_box(5.8, -5.75, -0.8, 1.6, 2.2, 0.4, "0.8 0.75 0.5"),
])

# ---- USB-C HRO: metal shell + opening (no stock model exists for it) ----
write_wrl("usb_c_hro.wrl", [
    wrl_box(0, 0, 1.62, 8.94, 7.3, 3.16, "0.75 0.76 0.78"),
    wrl_box(0, -3.45, 1.62, 8.2, 0.7, 2.5, "0.1 0.1 0.1"),
])

# ---- JST SH battery connector (authored in back-side footprint frame) ----
write_wrl("jst_sh_2p.wrl", [
    wrl_box(0, -0.45, 0.78, 4.0, 4.25, 1.55, "0.92 0.9 0.85"),
    wrl_box(0, 2.0, 0.35, 1.6, 0.9, 0.6, "0.85 0.75 0.4"),
    wrl_box(0, -2.35, 0.7, 3.1, 0.5, 1.0, "0.2 0.2 0.2"),
])

STOCK = "${KICAD9_3DMODEL_DIR}"
PRJV = "${KIPRJMOD}/3dmodels"

def entry(path, off=(0, 0, 0), rot=(0, 0, 0)):
    return (f'    (model "{path}"\n'
            f'      (offset (xyz {off[0]:g} {off[1]:g} {off[2]:g}))\n'
            f'      (scale (xyz 1 1 1))\n'
            f'      (rotate (xyz {rot[0]:g} {rot[1]:g} {rot[2]:g}))\n'
            f'    )\n')

SWITCH_MODELS = (entry(f"{PRJV}/Gateron_KS-33.step")
                 + entry(f"{PRJV}/gateron_socket.wrl", off=(0, 0, -1.6)))

def models_for(ref, fpname):
    if fpname.endswith("SW_Gateron_KS33_HS"):
        return SWITCH_MODELS
    if fpname.endswith("D_SOD-123_Back"):
        return entry(f"{STOCK}/Diode_SMD.3dshapes/D_SOD-123.wrl")
    if fpname.endswith("ESP32-C6-MINI-1"):
        return entry(f"{PRJV}/esp32_c6_mini1.wrl")
    if fpname.endswith("USB_C_Receptacle_HRO_TYPE-C-31-M-12"):
        return entry(f"{PRJV}/usb_c_hro.wrl")
    if fpname.endswith("SOT-23-5"):
        return entry(f"{STOCK}/Package_TO_SOT_SMD.3dshapes/SOT-23-5.wrl")
    if fpname.endswith("SOT-23-6"):
        return entry(f"{STOCK}/Package_TO_SOT_SMD.3dshapes/SOT-23-6.wrl")
    if fpname.endswith("SOT-23"):
        return entry(f"{STOCK}/Package_TO_SOT_SMD.3dshapes/SOT-23.wrl")
    if fpname.endswith("JST_SH_SM02B_2pin_Back"):
        return entry(f"{PRJV}/jst_sh_2p.wrl")
    if fpname.endswith("SW_PUSH_6mm_THT"):
        return entry(f"{STOCK}/Button_Switch_THT.3dshapes/SW_PUSH_6mm.wrl")
    if fpname.endswith("SW_Slide_MSK12C02"):
        return entry(f"{PRJV}/slide_msk12c02.wrl")
    if fpname.endswith("LED_0603"):
        return entry(f"{STOCK}/LED_SMD.3dshapes/LED_0603_1608Metric.wrl")
    if fpname.endswith("RC_0603"):
        if ref and ref.startswith("C"):
            return entry(f"{STOCK}/Capacitor_SMD.3dshapes/C_0603_1608Metric.wrl")
        return entry(f"{STOCK}/Resistor_SMD.3dshapes/R_0603_1608Metric.wrl")
    return None

def patch_board(path):
    def paren_delta(line):
        d = 0
        in_str = False
        for ch in line:
            if ch == '"':
                in_str = not in_str
            elif not in_str:
                if ch == "(":
                    d += 1
                elif ch == ")":
                    d -= 1
        return d

    lines = open(path).read().splitlines(keepends=True)
    out = []
    fpname = None
    ref = None
    indent = None
    depth = 0
    added = 0
    for ln in lines:
        m = re.match(r'(\s+)\(footprint "([^"]+)"', ln)
        if m and fpname is None:
            indent = m.group(1)
            fpname = m.group(2)
            ref = None
            depth = paren_delta(ln)
            out.append(ln)
            continue
        if fpname:
            if ref is None:
                mr = re.search(r'\(property "Reference" "([^"]+)"', ln)
                if mr:
                    ref = mr.group(1)
            depth += paren_delta(ln)
            if depth == 0:      # this line closes the footprint
                mdl = models_for(ref, fpname)
                if mdl:
                    fixed = []
                    for mline in mdl.splitlines():
                        stripped = mline.lstrip()
                        lvl = 2 if (mline.startswith("    (") or mline.startswith("    )")) else 3
                        fixed.append(indent * lvl + stripped)
                    out.append("\n".join(fixed) + "\n")
                    added += 1
                fpname = None
        out.append(ln)
    open(path, "w").write("".join(out))
    print(f"{os.path.basename(path)}: {added} footprints got models")

def patch_pretty():
    pdir = os.path.join(PRJ, "kbd.pretty")
    for fn in os.listdir(pdir):
        fp = os.path.join(pdir, fn)
        txt = open(fp).read()
        if "(model" in txt:
            continue
        name = fn[:-len(".kicad_mod")]
        mdl = models_for(None, name)
        if not mdl:
            continue
        i = txt.rstrip().rfind(")")
        txt = txt[:i] + mdl + txt[i:]
        open(fp, "w").write(txt)
        print(f"kbd.pretty/{fn}: model added")

if __name__ == "__main__":
    patch_board(os.path.join(PRJ, "gateron_lp_kbd.kicad_pcb"))
    patch_pretty()

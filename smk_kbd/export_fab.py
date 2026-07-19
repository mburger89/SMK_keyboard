#!/usr/bin/env python3
"""Fill zones and export PCBWay-ready Gerbers + drill files.

Run this with KiCad's bundled Python so the pcbnew module is available.

macOS:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 export_fab.py
Windows:
  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" export_fab.py
Linux:
  python3 export_fab.py   (with kicad installed system-wide)

Output: fab/ directory + smk_kbd_gerbers.zip -> upload the zip to PCBWay.
"""
import os, zipfile
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, "smk_kbd.kicad_pcb")
OUT = os.path.join(HERE, "fab")
os.makedirs(OUT, exist_ok=True)

board = pcbnew.LoadBoard(BOARD)

# 1. fill the GND zones and save
filler = pcbnew.ZONE_FILLER(board)
filler.Fill(board.Zones())
pcbnew.SaveBoard(BOARD, board)
print("zones filled and board saved")

# 2. plot gerbers
pctl = pcbnew.PLOT_CONTROLLER(board)
popt = pctl.GetPlotOptions()
popt.SetOutputDirectory(OUT)
popt.SetPlotFrameRef(False)
popt.SetAutoScale(False)
popt.SetScale(1)
popt.SetMirror(False)
popt.SetUseGerberAttributes(True)
popt.SetUseGerberX2format(True)
popt.SetCreateGerberJobFile(True)
try:
    popt.SetSubtractMaskFromSilk(True)
except Exception:
    pass
try:
    popt.SetPlotValue(True)
    popt.SetPlotReference(True)
except Exception:
    pass

layers = [
    ("F_Cu",      pcbnew.F_Cu,      "Top copper"),
    ("B_Cu",      pcbnew.B_Cu,      "Bottom copper"),
    ("F_Mask",    pcbnew.F_Mask,    "Top mask"),
    ("B_Mask",    pcbnew.B_Mask,    "Bottom mask"),
    ("F_SilkS",   pcbnew.F_SilkS,   "Top silk"),
    ("B_SilkS",   pcbnew.B_SilkS,   "Bottom silk"),
    ("F_Paste",   pcbnew.F_Paste,   "Top paste"),
    ("B_Paste",   pcbnew.B_Paste,   "Bottom paste"),
    ("Edge_Cuts", pcbnew.Edge_Cuts, "Board outline"),
]
for name, lid, desc in layers:
    pctl.SetLayer(lid)
    pctl.OpenPlotfile(name, pcbnew.PLOT_FORMAT_GERBER, desc)
    pctl.PlotLayer()
pctl.ClosePlot()
print("gerbers plotted")

# 3. drill files (Excellon, PTH + NPTH separate)
writer = pcbnew.EXCELLON_WRITER(board)
writer.SetFormat(True)  # metric
offset = pcbnew.VECTOR2I(0, 0)
writer.SetOptions(False, False, offset, False)
writer.CreateDrillandMapFilesSet(OUT, True, False)
print("drill files written")

# 4. zip for PCBWay
zpath = os.path.join(HERE, "smk_kbd_gerbers.zip")
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(os.listdir(OUT)):
        z.write(os.path.join(OUT, f), f)
print(f"wrote {zpath} - upload this to PCBWay")

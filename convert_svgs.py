"""
convert_svgs.py
===============
Lit les SVG dans canton-ecosystem/logos/
Ecrit les PNG dans un dossier de sortie séparé (pas le même dossier)

Usage: python convert_svgs.py
"""

import os, sys
from pathlib import Path

# Source : dossier logos dans le repo
LOGOS_DIR = Path("canton-ecosystem/logos")

PNG_OUTPUT = Path("canton-ecosystem/logos-png")
PNG_OUTPUT.mkdir(parents=True, exist_ok=True)

try:
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
except ImportError:
    print("Installing svglib + reportlab...")
    os.system(f"{sys.executable} -m pip install svglib reportlab")
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM

svgs = list(LOGOS_DIR.glob("*.svg"))
print(f"Found {len(svgs)} SVG files\n")

ok, failed = 0, 0
for svg_path in svgs:
    png_path = PNG_OUTPUT / (svg_path.stem + ".png")
    try:
        drawing = svg2rlg(str(svg_path))
        if drawing:
            renderPM.drawToFile(drawing, str(png_path), fmt="PNG")
            print(f"  OK  {svg_path.name} -> {png_path}")
            ok += 1
        else:
            print(f"  SKIP {svg_path.name} - could not parse")
            failed += 1
    except Exception as e:
        print(f"  FAIL {svg_path.name} - {e}")
        failed += 1

print(f"\nDone - {ok} converted, {failed} skipped")
print(f"PNG files are in: {PNG_OUTPUT.resolve()}")
print("\nUpload the contents of that folder to GitHub:")
print("  canton-ecosystem/logos/ (replace SVGs with PNGs)")

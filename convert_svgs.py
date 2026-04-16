"""
convert_svgs.py
===============
Converts all SVG logos in canton-ecosystem/logos/ to PNG.
Requires: pip install cairosvg

Usage: python convert_svgs.py
"""

import os
from pathlib import Path

LOGOS_DIR = Path("canton-ecosystem/logos")

try:
    import cairosvg
except ImportError:
    print("Installing cairosvg...")
    os.system("pip install cairosvg")
    import cairosvg

svgs = list(LOGOS_DIR.glob("*.svg"))
print(f"Found {len(svgs)} SVG files to convert")

for svg_path in svgs:
    png_path = svg_path.with_suffix(".png")
    try:
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=128, output_height=128)
        os.remove(svg_path)  # remove original SVG
        print(f"  ✓ {svg_path.name} → {png_path.name}")
    except Exception as e:
        print(f"  ⚠ {svg_path.name} failed: {e}")

print(f"\nDone. {len(svgs)} SVGs converted to PNG.")
print("Now run: git add canton-ecosystem/logos/ && git commit -m 'chore: convert SVG logos to PNG' && git push origin dev")

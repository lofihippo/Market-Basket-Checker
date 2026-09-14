#!/usr/bin/env python
"""Crop a bounding region from a PDF page and render to PNG at high DPI."""
import sys
import pymupdf

pdf_path, page_idx, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
x0, y0, x1, y1 = (float(v) for v in sys.argv[4:8])
dpi = int(sys.argv[8]) if len(sys.argv) > 8 else 200

doc = pymupdf.open(pdf_path)
page = doc[page_idx]
clip = pymupdf.Rect(x0, y0, x1, y1)
pix = page.get_pixmap(dpi=dpi, clip=clip)
pix.save(out)
print(f"Saved {out} ({pix.width}x{pix.height}) from clip {clip}")

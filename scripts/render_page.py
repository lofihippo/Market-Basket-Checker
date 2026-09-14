#!/usr/bin/env python
"""Render a PDF page to PNG for visual inspection."""
import sys
import pymupdf

pdf_path = sys.argv[1]
page_idx = int(sys.argv[2])
out = sys.argv[3]
dpi = int(sys.argv[4]) if len(sys.argv) > 4 else 120

doc = pymupdf.open(pdf_path)
page = doc[page_idx]
pix = page.get_pixmap(dpi=dpi)
pix.save(out)
print(f"Saved {out} ({pix.width}x{pix.height})")

#!/usr/bin/env python
"""
Configuration for the Market Basket weekly flyer extractor.

This centralises the tunable heuristics so the pipeline can be re-run on a new
weekly PDF (whose layout/colors/section titles may drift) without editing the
extractor code. Load with `load_config(path)` to override defaults from a JSON
file, e.g.:

    {
      "non_products": ["new section header", ...],
      "colors": {"red": "0xff0000", "blue": "0x1b4491", ...}
    }
"""
from __future__ import annotations

import json
import os

# Default tunables. Colors are packed RGB ints (0xRRGGBB) as used by pymupdf
# span["color"].
DEFAULT_CONFIG = {
    # Text that must never be treated as a product item (section bars, page
    # titles, footer phrases). Lower-cased for matching.
    "non_products": [
        "more for your dollar",
        "market basket",
        "frozen",
        "dairy",
        "frozen food",
        "grocery specials",
        "bakery shelf",
        "snacks & beverages",
        "meat specials",
        "produce",
        "beef • pork • poultry",
        "antibiotic free & organic",
        "frozen meat department items",
        "beer & wine sale",
        "bottled water",
    ],

    # Store-location metadata patterns (town + street + hours) that must be
    # excluded from product names.
    "store_towns": [
        "Hanover", "Danvers", "Waltham", "Tewksbury", "Shrewsbury",
    ],
    "store_streets": [
        "Washington", "Endicott", "Market", "Main", "Hartford",
    ],

    # Promotional taglines that get stripped from product names.
    "taglines": [
        "Made With The Freshest & Finest Ingredients!",
        "Made With The Freshest & Finest",
        "Ingredients!",
        "Cut Fresh Daily",
        "Wild • All Natural",
        "Ocean Fresh",
    ],
}


def load_config(path=None):
    """Return the config dict, merged with an optional external JSON config."""
    cfg = {**DEFAULT_CONFIG}
    if path:
        with open(path, "r", encoding="utf-8") as f:
            overrides = json.load(f)
        for k, v in overrides.items():
            if isinstance(v, list):
                cfg[k] = cfg.get(k, []) + list(v)
            else:
                cfg[k] = v
    return cfg

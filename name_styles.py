"""Select title spans for the name styles present in the reference flyer.

This classifies text inside an already established region; it does not infer
product boundaries. White text is a conservative fallback for the reversed
Arial Black meat titles, because white is also widely used for badges.
"""
from __future__ import annotations

import re


_BLUE = 0x1B4491
_NAVY = 0x17224E
_PURPLE = 0x703996
_PRODUCE_BLUE = 0x3657A7

_HEADERS = {
    "frozen", "dairy", "produce", "meat specials", "grocery specials",
    "frozen food", "bakery shelf", "snacks & beverages",
    "bouquets & potted plants", "beef • pork • poultry",
    "antibiotic free & organic", "frozen meat department items",
    "delicatessen", "market’s cheese shoppe", "more for your dollar",
    "market basket", "health", "household & pet care", "& beauty care",
    "for your dollar",
    "make your own pizza!",
}
_BADGES = {
    "for", "all", "varieties", "at the", "deli", "plant", "based",
    "fresh", "cut", "daily", "fully", "cooked", "heat", "serve",
    "usable", "am", "pm", "pkg", "package", "pack", "bag", "lb", "oz",
}
_MEASUREMENT = re.compile(
    r"^(?:\d+(?:\.\d+)?\s*[-–]?\s*)+"
    r"(?:oz|lb|lbs|ltr|ml|g|kg|count|ct|pack|inch)\b", re.IGNORECASE
)


def _near(color, target, tolerance):
    return all(abs(((color >> shift) & 255) - ((target >> shift) & 255))
               <= tolerance for shift in (16, 8, 0))


def _non_title(text):
    normalized = " ".join(text.split()).casefold().strip(" .:")
    return (
        not any(char.isalpha() for char in text)
        or normalized in _HEADERS
        or normalized in {"in cooking", "bag"}
        or normalized.startswith(("save ", "compare & save", "store hours",
                                  "sale starts", "open regular hours"))
    )


def product_name_spans(spans, allow_white=False):
    """Return original title spans in input order, without modifying them.

    Blue retains the existing size behavior. Navy and purple titles require
    at least 10 points to exclude the meat layout's smaller qualifiers.
    White titles are considered only when ``allow_white`` is true and there
    is no colored title. Font metadata, when supplied, distinguishes the
    reference meat titles from white badges and other reversed text.
    """
    colored, white = [], []
    for span in spans:
        text = span["text"].strip()
        if _non_title(text):
            continue
        color = span["color"]
        size = span["size"]
        if _near(color, _BLUE, 25):
            colored.append(span)
        elif size >= 10 and (_near(color, _NAVY, 18)
                             or _near(color, _PURPLE, 20)):
            if not _MEASUREMENT.match(text):
                colored.append(span)
        elif size >= 10 and _near(color, _PRODUCE_BLUE, 12):
            if (not _MEASUREMENT.match(text)
                    and text.casefold().strip(" .:") not in _BADGES):
                colored.append(span)
        elif allow_white and size >= 10 and _near(color, 0xFFFFFF, 14):
            if text.casefold().strip(" .:") in _BADGES or _MEASUREMENT.match(text):
                continue
            font = re.sub(r"[^a-z]", "", span.get("font", "").casefold())
            # Without font metadata, all-capital lettering is a conservative
            # fallback for the same reversed meat titles.
            if ("arialblack" in font if font else text.isupper()):
                white.append(span)
    return colored or white

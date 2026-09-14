"""Strict, one-to-one comparison with an annotated flyer reference."""
from decimal import Decimal, InvalidOperation
import re
import unicodedata


def norm_text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("expected text")
    value = unicodedata.normalize("NFKC", value).translate(str.maketrans({
        "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-",
    }))
    return re.sub(r"\s+", " ", value).strip().casefold()


def norm_price(value):
    """Return (offer quantity, total dollars); never equate $99 with 99¢."""
    match = re.fullmatch(
        r"(?:(\d+)\s*for\s*)?(\$?)(\d+(?:\.\d+)?|\.\d+)\s*(¢?)",
        norm_text(value),
    )
    if not match or (match[2] and match[4]):
        raise ValueError("unrecognized price")
    quantity = int(match[1] or 1)
    if quantity < 1:
        raise ValueError("offer quantity must be positive")
    amount = Decimal(match[3]) / (100 if match[4] else 1)
    return quantity, amount


def norm_unit(value):
    value = norm_text(value).rstrip(".")
    return {"lbs": "lb", "pound": "lb", "pounds": "lb",
            "each": "ea", "package": "pkg"}.get(value, value)


def norm_savings(value):
    value = re.sub(r"\b(lb|ea|pkg)\.", r"\1", norm_text(value))
    if not value:
        return None
    match = re.fullmatch(
        r"save\s+(up to\s+)?(\$?(?:\d+(?:\.\d+)?|\.\d+)¢?)"
        r"(?:\s*(?:/|per\s+)?(lb|ea|pkg))?", value,
    )
    if not match:
        raise ValueError("unrecognized savings")
    return bool(match[1]), norm_price(match[2])[1], norm_unit(match[3])


def norm_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("expected numeric price_n")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("price_n must be finite")
    return number


FIELDS = {"item": norm_text, "price": norm_price, "unit": norm_unit,
          "savings": norm_savings, "details": norm_text, "price_n": norm_number}


def validate_reference(reference):
    """Reject incomplete or ambiguous ground truth instead of passing it."""
    if not isinstance(reference, list) or not reference:
        raise ValueError("reference must contain at least one offer")
    seen = set()
    for deal in reference:
        if not isinstance(deal, dict) or any(field not in deal for field in FIELDS):
            raise ValueError("reference offer is missing required fields")
        normalized = {field: normalize(deal[field]) for field, normalize in FIELDS.items()}
        name = normalized["item"]
        if not name or name in seen:
            raise ValueError("reference item names must be nonempty and unique")
        if normalized["price"][1] != normalized["price_n"]:
            raise ValueError(f"inconsistent reference price_n for {deal['item']}")
        seen.add(name)


def compare_deals(actual, reference):
    """Compare all fields; truncated names and duplicate outputs cannot pass.

    Reference names must uniquely identify offers. Details retain their word
    order: only typography, whitespace, and capitalization are normalized.
    """
    validate_reference(reference)
    expected = {norm_text(deal["item"]): deal for deal in reference}
    seen = set()
    differences, unexpected = [], []
    passed = 0
    for deal in actual:
        try:
            key = norm_text(deal.get("item")) if isinstance(deal, dict) else ""
        except ValueError:
            key = ""
        if key not in expected or key in seen:
            unexpected.append(deal)
            continue
        seen.add(key)
        ref = expected[key]
        before = len(differences)
        for field, normalize in FIELDS.items():
            try:
                equal = field in deal and normalize(deal[field]) == normalize(ref[field])
            except (ValueError, InvalidOperation):
                equal = False
            if not equal:
                differences.append({"item": ref["item"], "field": field,
                                    "expected": ref[field], "actual": deal.get(field),
                                    "missing_field": field not in deal})
        passed += len(differences) == before
    missing = [deal for name, deal in expected.items() if name not in seen]
    return {"ok": not (missing or unexpected or differences), "matched": len(seen),
            "passed": passed, "missing": missing, "unexpected": unexpected,
            "differences": differences}

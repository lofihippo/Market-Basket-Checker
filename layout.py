"""Column boundaries from the flyer's vector divider rules."""
import pymupdf


def vertical_dividers(page):
    """Return thin, tall drawing bounds used to separate product columns."""
    return [pymupdf.Rect(drawing["rect"]) for drawing in page.get_drawings()
            if drawing["rect"].width <= 3 and drawing["rect"].height >= 35]


def column_bounds(box, dividers, page_rect):
    """Find the enclosing lane at a title's vertical center."""
    cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    active = [r for r in dividers if r.y0 - 8 <= cy <= r.y1 + 8]
    left = max((r.x1 for r in active if r.x1 < cx), default=page_rect.x0)
    right = min((r.x0 for r in active if r.x0 > cx), default=page_rect.x1)
    return left, right


def crosses_divider(first, second, dividers):
    """Whether two title fragments lie on opposite sides of a divider."""
    ax, ay = (first.x0 + first.x1) / 2, (first.y0 + first.y1) / 2
    bx, by = (second.x0 + second.x1) / 2, (second.y0 + second.y1) / 2
    return any(min(ax, bx) < (r.x0 + r.x1) / 2 < max(ax, bx)
               and r.y0 - 8 <= min(ay, by) and max(ay, by) <= r.y1 + 8
               for r in dividers)


def changes_divider_row(first, second, dividers):
    """A new band of column rules starts a separate row of offers."""
    ay = (first.y0 + first.y1) / 2
    by = (second.y0 + second.y1) / 2
    active = [r for r in dividers
              if first.x0 - 95 <= r.x0 <= first.x1 + 95
              and r.y0 - 8 <= ay <= r.y1 + 8]
    return bool(active) and not (min(r.y0 for r in active) - 8 <= by
                                 <= max(r.y1 for r in active) + 8)

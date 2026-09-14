"""Assign descriptive spans to one established offer at a time."""
import pymupdf


def span_box(spans):
    boxes = [pymupdf.Rect(span['bbox']) for span in spans]
    return pymupdf.Rect(min(b.x0 for b in boxes), min(b.y0 for b in boxes),
                        max(b.x1 for b in boxes), max(b.y1 for b in boxes))


def assign_fields(spans, contexts):
    """Partition table spans, preserving title/price ownership explicitly.

    Each context has group, run, lane, and bbox (the field region). Descriptive
    text is assigned once; close competing matches are reported for review.
    """
    result = [[] for _ in contexts]
    issues = [[] for _ in contexts]
    fixed = {}
    for i, context in enumerate(contexts):
        for span in context['group'] + context['run']['spans']:
            previous = fixed.setdefault(id(span), i)
            if previous != i:
                issues[i].append('shared_price_or_title')
                issues[previous].append('shared_price_or_title')
    for span in spans:
        if id(span) in fixed:
            result[fixed[id(span)]].append(span)
            continue
        sb = pymupdf.Rect(span['bbox'])
        cx, cy = (sb.x0 + sb.x1) / 2, (sb.y0 + sb.y1) / 2
        candidates = []
        for i, context in enumerate(contexts):
            box = context['bbox']
            if not (box.x0 <= cx <= box.x1 and box.y0 <= cy <= box.y1):
                continue
            price = span_box(context['run']['spans'])
            dx = max(price.x0 - sb.x1, sb.x0 - price.x1, 0)
            score = dx + .2 * abs(cy - context['run']['y'])
            candidates.append((score, i))
        candidates.sort()
        if candidates:
            result[candidates[0][1]].append(span)
            if len(candidates) > 1 and candidates[1][0] - candidates[0][0] < 2:
                issues[candidates[0][1]].append('ambiguous_detail_ownership')
    return result, issues


def split_cell_regions(cell_spans, runs, bbox):
    """Split adjacent offers in two dimensions using gaps between prices.

    Boundaries use facing price edges, not the midpoint of price centers:
    this keeps the shrimp bag/price label with shrimp rather than Gold's sauce.
    """
    boxes = [span_box(run['spans']) for run in runs]
    regions = []
    for i, box in enumerate(boxes):
        region = pymupdf.Rect(bbox)
        cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
        for j, other in enumerate(boxes):
            if i == j:
                continue
            ox, oy = (other.x0 + other.x1) / 2, (other.y0 + other.y1) / 2
            # Stacked price boxes share a column; adjacent ones split by x.
            overlap = min(box.x1, other.x1) - max(box.x0, other.x0)
            if overlap > .5 * min(box.width, other.width):
                if oy < cy:
                    region.y0 = max(region.y0, (other.y1 + box.y0) / 2)
                else:
                    region.y1 = min(region.y1, (box.y1 + other.y0) / 2)
            elif ox < cx:
                region.x0 = max(region.x0, (other.x1 + box.x0) / 2)
            else:
                region.x1 = min(region.x1, (box.x1 + other.x0) / 2)
        regions.append(region)
    groups = [[] for _ in runs]
    fixed = {id(s): i for i, run in enumerate(runs) for s in run['spans']}
    for span in cell_spans:
        if id(span) in fixed:
            groups[fixed[id(span)]].append(span)
            continue
        box = pymupdf.Rect(span['bbox'])
        center = pymupdf.Point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
        eligible = [i for i, region in enumerate(regions) if region.contains(center)]
        if eligible:
            groups[eligible[0]].append(span)
    return list(zip(regions, groups))

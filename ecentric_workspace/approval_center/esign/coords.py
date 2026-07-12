# Copyright (c) 2026, eCentric and contributors
"""Canonical placement coordinate system for the bundled PDF placement editor.

This module is deliberately frappe-free and side-effect-free so the conversion is
deterministic and fully unit-testable, and so the SAME math can be mirrored 1:1 in the
browser editor (esign/ui/pdf_placement_editor.html).

CANONICAL SYSTEM (the only thing persisted / validated by the backend):
  * origin = TOP-LEFT of the UNROTATED PDF page (matches package.validate_placement_geometry
    which validates x/y/width/height in points against the mediabox with a top-left origin);
  * +x = right, +y = down; units = PDF points (1/72 inch);
  * page dimensions = the page's UNROTATED mediabox (width_pt, height_pt);
  * page_index is 1-based.

VIEWPORT SYSTEM (what PDF.js draws on screen):
  * PDF.js renders the page already rotated by the page /Rotate value (0/90/180/270,
    clockwise) at a scale factor S (CSS px per rendered point);
  * viewport origin = TOP-LEFT of the rendered canvas, +x right, +y down, units = CSS px.

The editor draws rectangles in viewport px; we convert to canonical points before sending
to the backend, and the backend re-validates authoritatively. Frontend numbers are never
trusted for authorization or bounds - this is purely a deterministic display transform.
"""

_ROT = (0, 90, 180, 270)


def normalize_rotation(rotation):
    """Coerce any PDF /Rotate into {0,90,180,270}. Non-multiples of 90 fail closed to 0."""
    try:
        r = int(rotation or 0) % 360
    except (TypeError, ValueError):
        return 0
    return r if r in _ROT else 0


def rendered_page_size(page_pt, rotation):
    """(rendered_width_pt, rendered_height_pt) for the on-screen rotated page."""
    w, h = float(page_pt[0]), float(page_pt[1])
    return (h, w) if normalize_rotation(rotation) in (90, 270) else (w, h)


def canonical_point_to_rendered(cx, cy, page_pt, rotation):
    """Map a canonical (unrotated, top-left, points) point to rendered (rotated, top-left,
    points) coordinates. Clockwise display rotation, matching PDF /Rotate semantics."""
    w, h = float(page_pt[0]), float(page_pt[1])
    r = normalize_rotation(rotation)
    if r == 0:
        return (cx, cy)
    if r == 90:
        return (h - cy, cx)
    if r == 180:
        return (w - cx, h - cy)
    return (cy, w - cx)  # 270


def rendered_point_to_canonical(rx, ry, page_pt, rotation):
    """Inverse of canonical_point_to_rendered."""
    w, h = float(page_pt[0]), float(page_pt[1])
    r = normalize_rotation(rotation)
    if r == 0:
        return (rx, ry)
    if r == 90:
        return (ry, h - rx)
    if r == 180:
        return (w - rx, h - ry)
    return (w - ry, rx)  # 270


def _rect_from_corners(ax, ay, bx, by):
    x = min(ax, bx)
    y = min(ay, by)
    return {"x": x, "y": y, "width": abs(bx - ax), "height": abs(by - ay)}


def viewport_rect_to_canonical(rect_px, page_pt, scale, rotation):
    """Convert a viewport-pixel rectangle {x,y,width,height} (top-left) into a canonical
    point rectangle. `scale` = CSS px per rendered point (>0). Rounds to 3 decimals so the
    same input always yields the same persisted value (determinism for idempotency/hashing).
    """
    s = float(scale)
    if s <= 0:
        raise ValueError("scale must be > 0")
    # viewport px -> rendered points
    rx1 = float(rect_px["x"]) / s
    ry1 = float(rect_px["y"]) / s
    rx2 = (float(rect_px["x"]) + float(rect_px["width"])) / s
    ry2 = (float(rect_px["y"]) + float(rect_px["height"])) / s
    # rendered points -> canonical points (transform both corners, then bound)
    c1 = rendered_point_to_canonical(rx1, ry1, page_pt, rotation)
    c2 = rendered_point_to_canonical(rx2, ry2, page_pt, rotation)
    out = _rect_from_corners(c1[0], c1[1], c2[0], c2[1])
    return {k: round(v, 3) for k, v in out.items()}


def canonical_rect_to_viewport(rect_pt, page_pt, scale, rotation):
    """Inverse of viewport_rect_to_canonical - used to render existing persisted placements
    back onto the rotated viewport."""
    s = float(scale)
    if s <= 0:
        raise ValueError("scale must be > 0")
    cx1 = float(rect_pt["x"])
    cy1 = float(rect_pt["y"])
    cx2 = cx1 + float(rect_pt["width"])
    cy2 = cy1 + float(rect_pt["height"])
    r1 = canonical_point_to_rendered(cx1, cy1, page_pt, rotation)
    r2 = canonical_point_to_rendered(cx2, cy2, page_pt, rotation)
    out = _rect_from_corners(r1[0] * s, r1[1] * s, r2[0] * s, r2[1] * s)
    return {k: round(v, 3) for k, v in out.items()}


def is_within_page(rect_pt, page_pt, tol=1.0):
    """True if a canonical rectangle stays inside the unrotated mediabox (matches the
    backend rule). Zero/negative-area rectangles are rejected."""
    w, h = float(page_pt[0]), float(page_pt[1])
    x, y = float(rect_pt["x"]), float(rect_pt["y"])
    wd, ht = float(rect_pt["width"]), float(rect_pt["height"])
    if wd <= 0 or ht <= 0:
        return False
    return (x >= -tol and y >= -tol and (x + wd) <= (w + tol) and (y + ht) <= (h + tol))

# Copyright (c) 2026, eCentric and contributors
"""Shared shell-boundary helpers (slice-and-rebuild, byte-proof by construction).

Used by the module page syncs (alerts / reporting / pm). The transform NEVER
regex-substitutes business bytes: it locates the [legacy sidebar .. legacy
topbar] window via verified anchors, rebuilds ONLY that window from the
canonical renderers, and reassembles prefix + window + suffix, where prefix,
in-window business gap and suffix are the ORIGINAL byte slices. Callers then
assert post-conditions (single mount/topbar/bell/crumbs)."""
import re

from ecentric_workspace.shell import fallback as fb

SIDEBAR_OPEN = '<aside class="ec-sidebar"'
TOPBAR_RE = re.compile(r'<div class="topbar">')
CANON_SIDEBAR_RE = re.compile(r'<aside class="ec-shell-mount".*?</aside>', re.S)
CANON_TOPBAR_RE = re.compile(r'<div class="ec-shell-topbar" data-ec-shell-topbar="1">.*?'
                             r'data-ec-shell-header-right="1">.*?</div></div>', re.S)


def walk_div(ms, start):
    """Return index just past the </div> closing the div opened at `start`."""
    depth = 0
    for m in re.compile(r'<div\b|</div>').finditer(ms, start):
        if m.group(0) == "</div>":
            depth -= 1
            if depth == 0:
                return m.end()
        else:
            depth += 1
    raise ValueError("unbalanced div from %d" % start)


def find_window(ms):
    """(side0, side1, top0, top1) for legacy `.ec-sidebar` + `.topbar`.
    Accepts already-migrated pages (canonical mount/topbar) for idempotency:
    returns the canonical zones instead."""
    m_side = CANON_SIDEBAR_RE.search(ms)
    if m_side:
        side0, side1 = m_side.span()
    else:
        side0 = ms.index(SIDEBAR_OPEN)
        side1 = ms.index("</aside>", side0) + len("</aside>")
    m_top = CANON_TOPBAR_RE.search(ms)
    if m_top:
        top0, top1 = m_top.span()
    else:
        t = TOPBAR_RE.search(ms, side1)
        if not t:
            raise ValueError("no legacy/canonical topbar after sidebar")
        top0 = t.start()
        top1 = walk_div(ms, top0)
    if not (side0 < side1 <= top0 < top1):
        raise ValueError("zone window out of order")
    return side0, side1, top0, top1


def mount_html(route):
    return ('<aside class="ec-shell-mount" data-ec-shell="1" '
            'aria-label="Điều hướng eCentric">%s</aside>' % fb.render_mount_inner(route))


def topbar_html(route, detail_html=None):
    return ('<div class="ec-shell-topbar" data-ec-shell-topbar="1">%s</div>'
            % fb.render_topbar_inner(route, detail_html))


def assert_post(new, route, extra_markers=()):
    for marker, n in (('data-ec-shell="1"', 1),
                      ('data-ec-notification-bell="1"', 1),
                      ('data-ec-shell-topbar="1"', 1),
                      ('data-ec-shell-crumbs="1"', 1),
                      ('data-ec-shell-header-right="1"', 1)) + tuple(extra_markers):
        if new.count(marker) != n:
            raise ValueError("post-condition %s x%s (want %s) on %s"
                             % (marker, new.count(marker), n, route))

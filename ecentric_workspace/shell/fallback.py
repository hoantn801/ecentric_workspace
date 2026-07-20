# Copyright (c) 2026, eCentric and contributors
"""Static Shared-Shell fallback renderer (Smoothness Stabilization).

Renders the COMPLETE sidebar + header-right markup as static HTML from the
same canonical registry (shell.nav.compose()), so every migrated page paints a
full shell on first paint with ZERO JavaScript. ec_shell.js then HYDRATES the
same geometry (identical classes/structure) -- no layout shift, no reveal
masking, no blank sidebar.

Contract parity with ec_shell.js is deliberate and test-enforced:
- identical class names (.ec-shell-head/-search/-nav/-item/-foot/...)
- identical ICONS paths (test compares against the JS source)
- identical active-route scoring (matchActive port)
- exactly ONE static notification bell, placed in the page's header-right slot
  (data-ec-notification-bell="1" -- the NC bundle binds to it even before the
  shell boots).

CLI (regenerates every migrated page in the repo):
    python -m ecentric_workspace.shell.fallback --repo <repo-root> [--check]
"""
import io
import os
import re
import sys

from ecentric_workspace.shell import nav as shell_nav

ICONS = {
    "home":  '<path d="M3 12l9-9 9 9M5 10v10h14V10"/>',
    "check": '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    "chart": '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
    "doc":   '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M9 15l2 2 4-4"/>',
    "bell":  '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    "burger": '<path d="M3 6h18M3 12h18M3 18h18"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>',
}
LOGO_SRC = "/files/eCentric%20logo%20-%20mini.png"


def _svg(name):
    return '<svg viewBox="0 0 24 24" aria-hidden="true">%s</svg>' % ICONS.get(name, ICONS["doc"])


def _esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _norm(p):
    p = (p or "/").split("?")[0].split("#")[0]
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p or "/"


def match_active(items, pathname):
    """Port of ec_shell.js matchActive (same scoring; flattens children)."""
    path = _norm(pathname)
    flat = []
    for it in items:
        flat.append(it)
        flat.extend(it.get("children", []))
    best_key, best = None, 0
    for it in flat:
        score = 0
        if _norm(it["route"]) == path:
            score = 1000 + len(it["route"])
        for pat in it.get("active_patterns", []):
            s = 0
            if pat.endswith("/*"):
                base = _norm(pat[:-2])
                if path == base or path.startswith(base + "/"):
                    s = 500 + len(base)
            elif _norm(pat) == path:
                s = 900 + len(pat)
            score = max(score, s)
        if score > best:
            best, best_key = score, it["key"]
    return best_key


def _item_html(it, active_key, extra_cls=""):
    act = " ec-shell-active" if it["key"] == active_key else ""
    cur = ' aria-current="page"' if act else ""
    return ('<a class="ec-shell-item%s%s" href="%s"%s>%s<span>%s</span></a>'
            % (extra_cls, act, _esc(it["route"]), cur, _svg(it["icon"]), _esc(it["label"])))


def render_nav(items, active_key):
    """The static nav list -- IDENTICAL structure to ec_shell.js navHtml()."""
    groups, order = {}, []
    for it in items:
        g = it.get("group", "")
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(it)
    h = []
    for g in order:
        lone_parent = len(groups[g]) == 1 and groups[g][0].get("children")
        if g and not lone_parent:
            h.append('<div class="ec-shell-grouplabel">%s</div>' % _esc(g))
        for it in groups[g]:
            kids = it.get("children") or []
            if kids:
                child_active = any(c["key"] == active_key for c in kids)
                exp = "true" if child_active else "false"
                hid = "" if child_active else " hidden"
                h.append('<button type="button" class="ec-shell-item ec-shell-subtoggle" '
                         'data-ec-shell-subtoggle="%s" aria-expanded="%s">%s<span>%s</span>'
                         '<svg class="ec-shell-chev" viewBox="0 0 24 24" aria-hidden="true">'
                         '<path d="m6 9 6 6 6-6"/></svg></button>'
                         % (_esc(it["key"]), exp, _svg(it["icon"]), _esc(it["label"])))
                h.append('<div class="ec-shell-children"%s data-ec-shell-children="%s">%s</div>'
                         % (hid, _esc(it["key"]),
                            "".join(_item_html(c, active_key, " ec-shell-child") for c in kids)))
            else:
                h.append(_item_html(it, active_key))
    # ec-shell-fallback kept on the container for backward-compatible tests
    return ('<nav class="ec-shell-nav ec-shell-fallback" aria-label="Điều hướng chính">%s</nav>'
            % "".join(h))


def render_mount_inner(route):
    """Full static sidebar for a page at `route` (head + search + nav + foot).
    Same geometry as the hydrated shell; ec_shell.js replaces it in place."""
    items = shell_nav.compose()
    active = match_active(items, route)
    head = ('<div class="ec-shell-head">'
            '<a class="ec-shell-brand" href="/">'
            '<img class="ec-shell-logoimg" src="%s" alt="eCentric">'
            '<span class="ec-shell-logo" hidden>eC</span>'
            '<span class="ec-shell-brandname">eCentric</span></a>'
            '</div>' % LOGO_SRC)
    search = ('<div class="ec-shell-search">%s'
              '<input class="ec-shell-search-in" type="text" placeholder="Tìm chức năng…" '
              'role="combobox" aria-expanded="false" aria-autocomplete="list" '
              'aria-label="Tìm chức năng" autocomplete="off" spellcheck="false">'
              '<button type="button" class="ec-shell-search-clear" '
              'data-ec-shell-search-clear="1" hidden aria-label="Xóa tìm kiếm">&times;</button>'
              '</div><div class="ec-shell-search-results" role="listbox" hidden></div>'
              % _svg("search"))
    foot = ('<div class="ec-shell-foot">'
            '<a class="ec-shell-usercard" href="/app/user">'
            '<span class="ec-shell-avatar">•</span>'
            '<span class="ec-shell-username">Tài khoản</span></a>'
            '</div>')
    return head + search + render_nav(items, active) + foot


def render_tbright_inner():
    """Static header-right content: reserved Action Center slot + THE single
    notification bell (NC binds to the marker with or without the shell)."""
    return ('<span class="ec-shell-actionslot" data-ec-shell-action-slot="1" aria-hidden="true"></span>'
            '<a class="ec-shell-iconbtn" href="/app/notification-log" '
            'data-ec-notification-bell="1" aria-label="Thông báo" title="Thông báo">%s</a>'
            % _svg("bell"))


MOUNT_RE = re.compile(r'(<aside class="ec-shell-mount"[^>]*>).*?(</aside>)', re.S)
TBRIGHT_RE = re.compile(r'(<div class="ec-shell-tbright" data-ec-shell-header-right="1">).*?(</div>)', re.S)


def page_route_map(repo):
    """slug/file -> route for every migrated page in the repo."""
    out = {}
    fe = os.path.join(repo, "ecentric_workspace", "approval_center", "frontend")
    for f in sorted(os.listdir(fe)):
        if f.endswith(".main_section.html"):
            slug = f[:-len(".main_section.html")]
            if slug == "approvals":
                route = "/approvals"
            elif slug == "approvals_dashboard":
                route = "/approvals/dashboard"
            else:
                route = "/approvals/" + slug.replace("_", "-")
            out[os.path.join(fe, f)] = route
    # exact route aliases that differ from slug rules
    fix = {"employee_info_update": "/approvals/employee-information-update",
           "late_early_out": "/approvals/late-in-early-out",
           "affiliate_bonus": "/approvals/affiliate-bonus-request",
           "asset_damage_loss": "/approvals/asset-damage-loss"}
    for slug, route in fix.items():
        p = os.path.join(fe, slug + ".main_section.html")
        if p in out:
            out[p] = route
    lp = os.path.join(repo, "ecentric_workspace", "legacy_pages")
    for slug in sorted(os.listdir(lp)):
        ps = os.path.join(lp, slug, "page_sync.py")
        ms = os.path.join(lp, slug, "main_section.html")
        if os.path.isfile(ps) and os.path.isfile(ms):
            m = re.search(r'ROUTE = "([^"]+)"', io.open(ps, encoding="utf-8").read())
            if m:
                out[ms] = "/" + m.group(1)
    return out


def regenerate(repo, check=False):
    changed, skipped = [], []
    for path, route in sorted(page_route_map(repo).items()):
        src = io.open(path, encoding="utf-8").read()
        if 'data-ec-shell="1"' not in src:
            skipped.append(path)
            continue
        inner = render_mount_inner(route)
        new = MOUNT_RE.sub(lambda m: m.group(1) + inner + m.group(2), src, count=1)
        if TBRIGHT_RE.search(new):
            new = TBRIGHT_RE.sub(lambda m: m.group(1) + render_tbright_inner() + m.group(2), new, count=1)
        if new != src:
            if not check:
                io.open(path, "w", encoding="utf-8", newline="").write(new)
            changed.append(path)
        assert new.count('data-ec-notification-bell="1"') <= 1
    return changed, skipped


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    changed, skipped = regenerate(a.repo, check=a.check)
    print("%s %d page(s); %d not opted-in (skipped)"
          % ("WOULD UPDATE" if a.check else "UPDATED", len(changed), len(skipped)))
    return 1 if (a.check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())

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
    "reminder": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "inbox": '<path d="M4 13h4l2 3h4l2-3h4"/><path d="M4 13V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7"/><path d="M4 13v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "repeat": '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 22l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>',
    "inbox2": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 13h5l1 2h6l1-2h5"/>',
    "briefcase": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    "building": '<rect x="4" y="3" width="16" height="18" rx="1"/><path d="M9 8h2M13 8h2M9 12h2M13 12h2M9 16h2M13 16h2"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 10h18"/>',
    "wallet": '<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M8 15h2"/>',
    "target": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1"/>',
    "activity": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/>',
    "book": '<path d="M4 19a2 2 0 0 1 2-2h14V3H6a2 2 0 0 0-2 2z"/><path d="M4 19a2 2 0 0 0 2 2h14v-4"/>',
    "userplus": '<circle cx="9" cy="8" r="4"/><path d="M3 21v-1a6 6 0 0 1 12 0v1M19 8v6M16 11h6"/>',
    "message": '<path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
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
            % (extra_cls + (" ec-shell-item-soon" if it.get("soon") else ""), act, _esc(it["route"]), cur, _svg(it["icon"]), _esc(it["label"])))


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
    items = shell_nav.compose(shell_nav.resolve_context(route))
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
    """Canonical header-right: exactly THREE global slots (Global Header phase).
    1. Reminder / Action Center -- inert disabled placeholder carrying the
       frozen extension marker data-ec-shell-action-slot="1". NO business data
       model behind it yet -- shell contract only.
    2. Notification bell -- UNCHANGED frozen NC marker contract
       (data-ec-notification-bell="1"), the ONLY bell on the page.
    3. Settings -- prepared inert slot (data-ec-shell-settings-slot="1");
       no governed settings destination exists, so it is disabled, not fake.
    Home/Help are deliberately ABSENT from the global header: both already
    live in the sidebar (brand link -> / ; HƯỚNG DẪN group)."""
    return ('<button type="button" class="ec-shell-iconbtn ec-shell-slot-disabled" '
            'data-ec-shell-action-slot="1" disabled aria-disabled="true" '
            'title="Nhắc việc (sắp ra mắt)" aria-label="Nhắc việc (sắp ra mắt)">%s</button>'
            '<a class="ec-shell-iconbtn" href="/app/notification-log" '
            'data-ec-notification-bell="1" aria-label="Thông báo" title="Thông báo">%s</a>'
            '<button type="button" class="ec-shell-iconbtn ec-shell-slot-disabled" '
            'data-ec-shell-settings-slot="1" disabled aria-disabled="true" '
            'title="Cài đặt (sắp ra mắt)" aria-label="Cài đặt (sắp ra mắt)">%s</button>'
            % (_svg("reminder"), _svg("bell"), _svg("gear")))


def _crumb_target(route):
    """Resolve route -> (registry item, group label) via the SAME matcher the
    shell uses. Children resolve to themselves; their crumb group falls back
    to the parent's group (registry stays the single source of truth)."""
    items = shell_nav.compose(shell_nav.resolve_context(route))
    key = match_active(items, route)
    parent_group = {}
    flat = []
    for it in items:
        flat.append(it)
        for ch in it.get("children") or []:
            flat.append(ch)
            parent_group[ch["key"]] = it.get("group") or ""
    it = next((x for x in flat if x["key"] == key), None)
    if it is None:
        return None, ""
    return it, (it.get("group") or parent_group.get(it["key"], ""))


def crumbs_inner(route, detail_html=None):
    """Registry-derived breadcrumb inner: [Group /] Item [/ detail].
    - Item label/route come ONLY from the canonical registry entry matched by
      match_active (no second route map, no hardcoded labels).
    - Item renders as a LINK when a detail suffix follows or when the page is
      a pattern-matched descendant; as the CURRENT element when it IS the page.
    - detail_html (optional, page-owned) is carried VERBATIM so live nodes
      like <strong id="pageTitle"> survive regeneration untouched."""
    it, group = _crumb_target(route)
    if it is None:
        return detail_html or ""
    h = []
    if group:
        h.append('<span class="ec-shell-crumb-group">%s</span>' % _esc(group))
        h.append('<span class="sep ec-shell-crumb-sep">/</span>')
    linked = bool(detail_html) or _norm(it["route"]) != _norm(route)
    if linked:
        h.append('<a class="ec-shell-crumblink" href="%s">%s</a>'
                 % (_esc(it["route"]), _esc(it["label"])))
    else:
        h.append('<strong class="ec-shell-crumb-current">%s</strong>' % _esc(it["label"]))
    if detail_html:
        h.append('<span class="sep ec-shell-crumb-sep">/</span>')
        h.append(detail_html)
    return "".join(h)


def crumbs_container(route, detail_html=None, extra_cls=""):
    cls = (extra_cls + " " if extra_cls else "") + "ec-shell-crumbs"
    return ('<div class="%s" data-ec-shell-crumbs="1">%s</div>'
            % (cls, crumbs_inner(route, detail_html)))


def make_detail(inner_html, node_id=None):
    """Canonical detail node (page-owned suffix). data-ec-shell-crumb-detail is
    the contract regeneration preserves verbatim and page JS may update."""
    idattr = ' id="%s"' % node_id if node_id else ""
    return ('<strong class="ec-shell-crumb-current ec-shell-crumb-detail" '
            'data-ec-shell-crumb-detail="1"%s>%s</strong>' % (idattr, inner_html))


def render_topbar_inner(route, detail_html=None):
    """Complete canonical topbar (crumbs + header-right) for pages that have
    NO page topbar of their own (docs/gbs-flow family). Pages WITH a topbar
    keep their container and only get canonical inners."""
    return (crumbs_container(route, detail_html)
            + '<div class="ec-shell-tbright" data-ec-shell-header-right="1">'
            + render_tbright_inner() + "</div>")


def render_quickaccess_inner():
    """Daily Cockpit "Truy cập nhanh" tiles -- derived from the SAME canonical
    registry as the sidebar (2C.2 rule: no second route catalog). After the
    context split this deliberately enumerates ALL contexts (compose_all):
    the sidebar is context-scoped, discovery is global. Skips non-navigable
    group toggles and the homepage itself. Regenerated together with
    mount/crumbs, so tiles can never drift from the registry."""
    items = shell_nav.compose_all()
    h = []
    for it in items:
        kids = it.get("children") or []
        flatset = kids if kids else [it]
        for x in flatset:
            if x.get("navigable") is False or x["key"] == "core.home":
                continue
            group = x.get("group") or it.get("group") or ""
            h.append(
                '<a class="ec-ck-qa-tile" href="%s">%s'
                '<span class="ec-ck-qa-label">%s</span>'
                '<span class="ec-ck-qa-group">%s</span></a>'
                % (_esc(x["route"]), _svg(x.get("icon") or it.get("icon") or "doc"),
                   _esc(x["label"]), _esc(group)))
    return "".join(h)


MOUNT_RE = re.compile(r'(<aside class="ec-shell-mount"[^>]*>).*?(</aside>)', re.S)
TBRIGHT_RE = re.compile(r'(<div class="ec-shell-tbright" data-ec-shell-header-right="1">).*?(</div>)', re.S)
CRUMBS_RE = re.compile(r'(<div class="[^"]*ec-shell-crumbs[^"]*" data-ec-shell-crumbs="1">)(.*?)(</div>)', re.S)
QUICKACCESS_RE = re.compile(r'(<div class="[^"]*ec-ck-qa[^"]*" data-ec-shell-quickaccess="1">).*?(</div>)', re.S)
DETAIL_RE = re.compile(r'<strong[^>]*data-ec-shell-crumb-detail="1"[^>]*>.*?</strong>', re.S)


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
        if CRUMBS_RE.search(new):
            def _crumbs(m):
                d = DETAIL_RE.search(m.group(2))
                return m.group(1) + crumbs_inner(route, d.group(0) if d else None) + m.group(3)
            new = CRUMBS_RE.sub(_crumbs, new, count=1)
        if QUICKACCESS_RE.search(new):
            new = QUICKACCESS_RE.sub(
                lambda m: m.group(1) + render_quickaccess_inner() + m.group(2), new, count=1)
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

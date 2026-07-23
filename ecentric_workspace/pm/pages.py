# Copyright (c) 2026, eCentric and contributors
"""PM SPA -> Shared Shell (context `pm`) -- SINGLE SIDEBAR, SPA-safe.

The visible PM internal rail is REMOVED: the canonical Shared Shell mount
is the only sidebar. The 7 PM views live in the `pm` nav context as flat
hash-route items (/pm#overview ...); clicking one only mutates the hash on
/pm, so the EXISTING PM router (`hashchange` -> go()) switches the view
with ZERO document reload (shell hash-aware active state, ec_shell.js
v1.12.0).

The old `<aside class="ec-sidebar">` becomes a HIDDEN compatibility bridge
(`#ec-pm-nav-bridge`, display:none): it retains `#pm-nav` (the 7 data-view
anchors) and the footer user-card (`#pm-av/#pm-uname/#pm-urole`) purely
because the shipped PM SPA has existing DOM bindings on them
(go()/fillUser). It is NOT navigation UI -- a TEMPORARY shim until the PM
SPA is refactored to bind the shell items directly.

`#pm-search` (business task/project search) is RELOCATED byte-exact into
the PM topbar (its id + Enter wiring preserved). The topbar keeps every
business control (#pm-preview, #tb-timer, #tb-new); the breadcrumb becomes
canonical registry crumbs (live `<strong id="pm-crumb">` kept as the detail
node), the raw bell becomes the canonical 3-slot header-right, the settings
stub is dropped. The live page's 2nd bell "occurrence" is a JS binding
string, not a DOM node -- structural bell count stays exactly 1."""
import re

import frappe
from frappe import _

from ecentric_workspace.shell import boundary

ROUTE = "pm"
NAME = "project-management"

HEADER_RE = re.compile(r'<div class="sidebar-header">.*?</div>\s*', re.S)
BACK_RE = re.compile(r'<div class="nav-label"[^>]*style="margin-top:10px;"[^>]*>.*?</div>\s*'
                     r'<a class="nav-item" href="/home">.*?</a>\s*', re.S)
FOOTER_RE = re.compile(r'<div class="sidebar-footer">.*?(?=</aside>)', re.S)
SEARCH_RE = re.compile(r'<div class="sidebar-search">.*?</div>\s*', re.S)
RAIL_ASIDE_RE = re.compile(r'<aside class="ec-sidebar">.*?</aside>', re.S)
TOPBAR_OPEN_RE = re.compile(r'<div class="topbar">')


def _find_rail(ms):
    """Locate the PM navigation rail CONTAINER enclosing #pm-nav, in ANY
    migration state (structural, not one class serialization):
      - <aside class="ec-sidebar"> ... </aside>   (legacy full OR dual-rail
        trimmed -- the 2nd rail the previous transform left in production)
      - <div id="ec-pm-nav-bridge" ...> ... </div>  (already single-sidebar)
    Returns (start, end, kind) where kind in {"aside", "bridge"}."""
    nav = ms.find('id="pm-nav"')
    if nav < 0:
        raise ValueError("PM rail not found (#pm-nav absent)")
    m = RAIL_ASIDE_RE.search(ms)
    if m and m.start() <= nav < m.end():
        return m.start(), m.end(), "aside"
    b = ms.find('<div id="ec-pm-nav-bridge"')
    if b >= 0:
        end = boundary.walk_div(ms, b)
        if b <= nav < end:
            return b, end, "bridge"
    raise ValueError("PM rail container around #pm-nav not recognized")
#: REAL production shape (UAT 417 root cause, verified live 2026-07-23):
#: the breadcrumb contains literal prefix text before the strong --
#: `<div class="breadcrumb">Project Management / <strong id="pm-crumb">...`.
#: `[^<]*` accepts exactly that (text-only prefix); any ELEMENT before the
#: strong keeps the guard strict and the transform refuses.
CRUMB_RE = re.compile(r'<div class="breadcrumb">([^<]*)<strong id="pm-crumb">(.*?)</strong>\s*</div>', re.S)
BELL_A_RE = re.compile(r'<a class="icon-btn" id="tb-bell"[^>]*data-ec-notification-bell="1"[^>]*>.*?</a>', re.S)
SETTINGS_RE = re.compile(r'\s*<button class="icon-btn" title="C(?:à|&#224;)i (?:đ|&#273;)(?:ặ|&#7863;)t">.*?</button>', re.S)
GRID_RE = re.compile(r'<style id="ec-pm-shell-grid">.*?</style>', re.S)
#: JINJA-SAFETY (production incident 2026-07-23): /pm renders through the
#: dynamic Frappe/Jinja pipeline, so injected markup must NEVER contain the
#: Jinja delimiters `{#`, `{{` or `{%`. The previous minified form emitted
#: `...1100px){#ec-pm-root{...` -> parsed as an unterminated Jinja comment
#: -> TemplateSyntaxError, page broken. CSS block boundaries therefore keep
#: explicit whitespace/newlines (see test_pm_injected_markup_is_jinja_safe).
GRID_STYLE = ('<style id="ec-pm-shell-grid">\n'
              '#ec-pm-root { grid-template-columns: 248px 1fr !important; }\n'
              '#ec-pm-nav-bridge { display: none !important; }\n'
              '.ec-pm-topsearch { position: relative; display: flex; align-items: center; '
              'flex: 1 1 260px; max-width: 340px; margin: 0 8px; }\n'
              '.ec-pm-topsearch .search-icon { position: absolute; left: 10px; '
              'width: 15px; height: 15px; color: #9ca3af; pointer-events: none; }\n'
              '.ec-pm-topsearch input { width: 100%; padding: 7px 10px 7px 30px; '
              'border: 1px solid #e5e7eb; border-radius: 8px; font-size: 13px; background: #f9fafb; }\n'
              '@media (max-width: 1100px) {\n'
              '  #ec-pm-root { grid-template-columns: 1fr !important; }\n'
              '  #ec-pm-root .ec-shell-mount { display: none; }\n'
              '}\n'
              '</style>')

JINJA_DELIMS = ("{#", "{{", "{%")


def _assert_jinja_safe(fragment, what):
    for d in JINJA_DELIMS:
        if d in fragment:
            raise ValueError("Jinja delimiter %r in injected %s" % (d, what))


def transform(ms):
    if ms.count('id="pm-nav"') != 1 or ms.count('id="pm-search"') != 1:
        raise ValueError("PM internal nav/search anchors missing")
    for biz in ('id="tb-timer"', 'id="tb-new"', 'id="pm-preview"', 'id="pm-crumb"'):
        if biz not in ms:
            raise ValueError("PM business control missing: %s" % biz)

    from ecentric_workspace.shell import fallback as fb
    ms_clean = GRID_RE.sub("", ms)

    # every SPA view anchor must survive BYTE-EXACT
    view_items = re.findall(r'<a class="nav-item" data-view=.*?</a>', ms_clean, re.S)
    if not view_items:
        raise ValueError("pm-nav view anchors not found")

    # --- locate the PM rail (structural, any state) + the topbar -----------
    r0, r1, kind = _find_rail(ms_clean)
    rail = ms_clean[r0:r1]
    tm = TOPBAR_OPEN_RE.search(ms_clean)
    if not tm:
        raise ValueError("PM topbar not found")
    t0 = tm.start()
    t1 = boundary.walk_div(ms_clean, t0)
    topbar = ms_clean[t0:t1]
    if not (r1 <= t0):
        raise ValueError("PM rail must precede the topbar")

    # --- #pm-search: extract from the rail (legacy/dual) or already moved --
    sm = SEARCH_RE.search(rail)
    if sm:
        search_block = sm.group(0).strip()
    elif 'class="ec-pm-topsearch"' in ms_clean:
        search_block = None                    # already relocated (idempotent)
    else:
        raise ValueError("#pm-search block not found")

    # --- hidden #pm-nav compatibility bridge (NOT navigation UI): keep
    #     #pm-nav (7 data-view anchors) + footer user-card so shipped SPA
    #     bindings (go(), fillUser) keep working; drop brand/back chrome and
    #     the relocated search.
    if kind == "aside":
        inner = rail[len('<aside class="ec-sidebar">'):-len('</aside>')]
        inner = HEADER_RE.sub("", inner, count=1)
        inner = BACK_RE.sub("", inner, count=1)
        inner = SEARCH_RE.sub("", inner, count=1)
        bridge = ('<div id="ec-pm-nav-bridge" hidden aria-hidden="true" '
                  'style="display:none">' + inner + '</div>')
    else:                                      # already a bridge -> rebuild
        inner = rail[rail.index(">") + 1:-len('</div>')]
        bridge = ('<div id="ec-pm-nav-bridge" hidden aria-hidden="true" '
                  'style="display:none">' + inner + '</div>')

    # single visible rail = the canonical shell mount. Add it (legacy) or
    # keep the one already present (dual-rail/single) -- the bridge REPLACES
    # the located rail in place.
    has_mount = 'data-ec-shell="1"' in ms_clean
    mount = boundary.mount_html("/pm")
    rail_zone = bridge if has_mount else (mount + bridge)

    # --- topbar: canonicalize crumbs/bell/settings ONLY if still legacy;
    #     relocate the extracted search either way ---------------------------
    relocated = ('<div class="ec-pm-topsearch">%s</div>' % search_block) if search_block else ""
    m = CRUMB_RE.search(topbar)
    if m:
        detail = ('<strong class="ec-shell-crumb-current ec-shell-crumb-detail" '
                  'data-ec-shell-crumb-detail="1" id="pm-crumb">%s</strong>' % m.group(2))
        new_topbar = CRUMB_RE.sub(
            lambda _m: '<div class="breadcrumb ec-shell-crumbs" data-ec-shell-crumbs="1">%s</div>'
                       % fb.crumbs_inner("/pm", detail), topbar, count=1)
        if not BELL_A_RE.search(new_topbar):
            raise ValueError("PM topbar bell anchor not found")
        new_topbar = BELL_A_RE.sub(
            '<div class="ec-shell-tbright" data-ec-shell-header-right="1">%s</div>'
            % fb.render_tbright_inner(), new_topbar, count=1)
        new_topbar = SETTINGS_RE.sub("", new_topbar, count=1)
    elif 'data-ec-shell-crumbs="1"' in topbar:
        new_topbar = topbar                    # already canonical (dual-rail/single)
    else:
        raise ValueError("PM topbar has neither legacy crumb nor canonical crumbs")
    if relocated:
        if '<div class="topbar-actions">' not in new_topbar:
            raise ValueError("PM topbar-actions anchor not found for search relocation")
        new_topbar = new_topbar.replace(
            '<div class="topbar-actions">', relocated + '<div class="topbar-actions">', 1)

    _assert_jinja_safe(GRID_STYLE, "ec-pm-shell-grid")
    _assert_jinja_safe(mount, "shell mount")
    _assert_jinja_safe(bridge, "pm-nav bridge")
    injected_topbar_delta = new_topbar.replace(topbar, "") if topbar in new_topbar else new_topbar
    _assert_jinja_safe(injected_topbar_delta, "topbar chrome")

    # assemble: prefix + rail_zone + gap(between rail & topbar) + topbar + suffix
    new = (ms_clean[:r0] + rail_zone + ms_clean[r1:t0]
           + new_topbar + GRID_STYLE + ms_clean[t1:])

    # SPA preservation proofs (byte-exact fragments)
    for v in view_items:
        if v not in new:
            raise ValueError("pm view anchor altered: %s" % v[:60])
    for biz in ('id="pm-search"', 'id="tb-timer"', 'id="tb-new"', 'id="pm-preview"',
                'id="pm-crumb"', 'id="pm-nav"', 'id="pm-av"', 'id="pm-uname"', 'id="pm-urole"'):
        if new.count(biz) != 1:
            raise ValueError("PM control lost/duplicated: %s" % biz)
    # single visible rail: the legacy sidebar CLASS is gone; the hidden bridge
    # exists exactly once and is display:none
    if 'class="ec-sidebar"' in new:
        raise ValueError("visible .ec-sidebar must be gone")
    if new.count('id="ec-pm-nav-bridge"') != 1:
        raise ValueError("hidden #pm-nav bridge must exist exactly once")
    if '#pm-search' not in "".join(re.findall(r'<div class="ec-pm-topsearch">.*?</div>', new, re.S)) \
            and new.count('class="ec-pm-topsearch"') != 1:
        raise ValueError("relocated #pm-search topbar block missing")
    # structural bell: exactly ONE bell ELEMENT (JS-string mentions ignored)
    if len(re.findall(r'<[a-zA-Z][^>]*data-ec-notification-bell="1"', new)) != 1:
        raise ValueError("PM bell element count != 1")
    if new.count('data-ec-shell="1"') != 1 or new.count('data-ec-shell-crumbs="1"') != 1 \
            or new.count('data-ec-shell-header-right="1"') != 1 \
            or new.count('<style id="ec-pm-shell-grid">') != 1:
        raise ValueError("PM shell post-conditions failed")
    return new


@frappe.whitelist(methods=["POST"])
def sync_pm_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the PM page."), frappe.PermissionError)
    if not frappe.db.exists("Web Page", NAME):
        return {"action": "skipped", "reason": "missing"}
    ms = frappe.db.get_value("Web Page", NAME, "main_section") or ""
    try:
        new = transform(ms)
    except ValueError as e:
        frappe.throw(_(str(e)))
    if new == ms:
        return {"action": "unchanged", "route": ROUTE}
    doc = frappe.get_doc("Web Page", NAME)
    doc.main_section = new
    doc.main_section_html = new
    doc.save(ignore_permissions=True)
    return {"action": "updated", "route": ROUTE,
            "len_before": len(ms), "len_after": len(new)}

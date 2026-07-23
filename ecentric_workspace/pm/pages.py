# Copyright (c) 2026, eCentric and contributors
"""PM SPA -> Shared Shell (context `pm`) -- SPA-SAFE integration.

The PM aside is NOT chrome: it hosts the SPA's internal view router
(#pm-nav data-view items) and PM-specific search (#pm-search). Design:
DUAL RAIL -- the canonical Shared Shell mount is inserted BEFORE a TRIMMED
PM rail (brand header, footer user-card and the '/home' back entry are
removed -- the shell provides brand/user/home), while #pm-search + #pm-nav
survive BYTE-EXACT. The topbar keeps ALL business controls (#pm-preview,
#tb-timer, #tb-new): only the breadcrumb becomes canonical crumbs (live
`<strong id="pm-crumb">` preserved as the detail contract node), the raw
bell anchor becomes the canonical 3-slot header-right, and the legacy
settings stub is dropped. A scoped style zone widens the SPA grid for the
extra rail. The live page's 2nd bell "occurrence" is a JS string (binding
comment), not a DOM node -- structural bell count stays exactly 1."""
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
CRUMB_RE = re.compile(r'<div class="breadcrumb">\s*<strong id="pm-crumb">(.*?)</strong>\s*</div>', re.S)
BELL_A_RE = re.compile(r'<a class="icon-btn" id="tb-bell"[^>]*data-ec-notification-bell="1"[^>]*>.*?</a>', re.S)
SETTINGS_RE = re.compile(r'\s*<button class="icon-btn" title="C(?:à|&#224;)i (?:đ|&#273;)(?:ặ|&#7863;)t">.*?</button>', re.S)
GRID_RE = re.compile(r'<style id="ec-pm-shell-grid">.*?</style>', re.S)
GRID_STYLE = ('<style id="ec-pm-shell-grid">'
              '#ec-pm-root{grid-template-columns:auto 248px 1fr !important;}'
              '#ec-pm-root .ec-sidebar .sidebar-search{margin-top:10px;}'
              '@media (max-width:1100px){#ec-pm-root{grid-template-columns:auto 1fr !important;}'
              '#ec-pm-root .ec-sidebar{display:none;}}'
              '</style>')


def transform(ms):
    if ms.count('id="pm-nav"') != 1 or ms.count('id="pm-search"') != 1:
        raise ValueError("PM internal nav/search anchors missing")
    for biz in ('id="tb-timer"', 'id="tb-new"', 'id="pm-preview"', 'id="pm-crumb"'):
        if biz not in ms:
            raise ValueError("PM business control missing: %s" % biz)

    ms_clean = GRID_RE.sub("", ms)
    s0, s1, t0, t1 = boundary.find_window(ms_clean)
    aside = ms_clean[s0:s1]
    topbar = ms_clean[t0:t1]

    # --- rail: trim chrome, keep SPA nav + search byte-exact ---------------
    if aside.startswith('<aside class="ec-sidebar"'):
        rail = HEADER_RE.sub("", aside, count=1)
        rail = BACK_RE.sub("", rail, count=1)
        rail = FOOTER_RE.sub("", rail, count=1)
    else:
        # idempotent path: canonical mount found; the trimmed rail is the
        # NEXT aside (kept from the previous run)
        rail = ""
    # every SPA view anchor must survive BYTE-EXACT (the '/home' back entry
    # and its 'Khác' label are chrome and are deliberately removed)
    view_items = re.findall(r'<a class="nav-item" data-view=.*?</a>', ms_clean, re.S)
    if not view_items:
        raise ValueError("pm-nav view anchors not found")

    # --- topbar: canonical crumbs + tbright, business controls preserved ---
    m = CRUMB_RE.search(topbar)
    if m:
        from ecentric_workspace.shell import fallback as fb
        detail = ('<strong class="ec-shell-crumb-current ec-shell-crumb-detail" '
                  'data-ec-shell-crumb-detail="1" id="pm-crumb">%s</strong>' % m.group(1))
        new_topbar = CRUMB_RE.sub(
            lambda _m: '<div class="breadcrumb ec-shell-crumbs" data-ec-shell-crumbs="1">%s</div>'
                       % fb.crumbs_inner("/pm", detail), topbar, count=1)
        if not BELL_A_RE.search(new_topbar):
            raise ValueError("PM topbar bell anchor not found")
        new_topbar = BELL_A_RE.sub(
            '<div class="ec-shell-tbright" data-ec-shell-header-right="1">%s</div>'
            % fb.render_tbright_inner(), new_topbar, count=1)
        new_topbar = SETTINGS_RE.sub("", new_topbar, count=1)
    else:
        if 'data-ec-shell-crumbs="1"' not in topbar:
            raise ValueError("PM topbar has neither legacy crumb nor canonical crumbs")
        new_topbar = topbar   # already canonical (idempotent)

    new = (ms_clean[:s0] + boundary.mount_html("/pm") + rail + ms_clean[s1:t0]
           + new_topbar + GRID_STYLE + ms_clean[t1:])

    # SPA preservation proofs (byte-exact fragments)
    for v in view_items:
        if v not in new:
            raise ValueError("pm view anchor altered: %s" % v[:60])
    for biz in ('id="pm-search"', 'id="tb-timer"', 'id="tb-new"', 'id="pm-preview"', 'id="pm-crumb"'):
        if new.count(biz) != 1:
            raise ValueError("PM control lost/duplicated: %s" % biz)
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

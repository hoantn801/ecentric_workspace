# Copyright (c) 2026, eCentric and contributors
"""Reporting pages (/weekly-update, /team-pulse) -> Shared Shell (`reporting`).

Both pages carry a STALE clone of the old Homepage sidebar + a tiny legacy
topbar (breadcrumb only, NO bell). Business asides (`wu-roadmap`,
`tp-ai-panel`), heavy Jinja (wu: ~97 tags) and all wu-*/tp-* scripts sit
OUTSIDE the [sidebar..topbar] window and are reassembled from the ORIGINAL
byte slices. The canonical topbar ADDS the page's first NC bell.
`?week=` deep links are untouched (query never affects zone anchors)."""
import re

import frappe
from frappe import _

from ecentric_workspace.shell import boundary

#: UAT hotfix (2026-07-23): both Reporting pages ship page CSS with GENERIC
#: selectors (* , a , input , nav (wu), header , main , svg , .topbar ...)
#: that clobber shell chrome geometry (measured: compressed/misstylized
#: mount vs the known-good /alerts). Business CSS stays byte-untouched; a
#: page-local ISOLATION zone re-asserts canonical shell geometry with class
#: specificity + !important. Values mirror ec_shell.bundle.css (source of
#: truth); this zone exists ONLY on the two Reporting pages.
ISOLATION_RE = re.compile(r'<style id="ec-reporting-shell-isolation">.*?</style>', re.S)
ISOLATION_STYLE = (
    '<style id="ec-reporting-shell-isolation">'
    '/* Reporting shell isolation -- neutralizes generic page selectors */'
    '.ec-shell-mount{background:#fff !important;border-right:1px solid #e5e7eb !important;'
    'display:flex !important;flex-direction:column !important;position:sticky !important;'
    'top:0 !important;height:100vh !important;overflow:hidden !important;'
    'width:auto !important;min-width:0 !important;padding:0 !important;margin:0 !important;'
    'font-family:Inter,system-ui,sans-serif !important;font-size:14px !important;'
    'line-height:1.5 !important;letter-spacing:normal !important;box-sizing:border-box !important;}'
    '.ec-shell-mount *{box-sizing:border-box !important;text-transform:none !important;}'
    '.ec-shell-head{display:flex !important;align-items:center !important;gap:9px !important;'
    'padding:14px 14px 10px !important;margin:0 !important;border:0 !important;background:transparent !important;}'
    '.ec-shell-brand{display:flex !important;align-items:center !important;gap:9px !important;'
    'text-decoration:none !important;padding:0 !important;margin:0 !important;}'
    '.ec-shell-brandname{font-weight:700 !important;font-size:14px !important;color:#111827 !important;}'
    '.ec-shell-logoimg{width:30px !important;height:30px !important;}'
    '.ec-shell-search{display:flex !important;align-items:center !important;'
    'margin:2px 12px 8px !important;padding:0 !important;position:relative !important;}'
    '.ec-shell-search-in{width:100% !important;padding:8px 30px 8px 32px !important;'
    'border:1px solid #e5e7eb !important;border-radius:8px !important;font-size:13px !important;'
    'background:#f9fafb !important;height:auto !important;margin:0 !important;box-shadow:none !important;}'
    '.ec-shell-nav{display:flex !important;flex-direction:column !important;gap:2px !important;'
    'padding:6px 10px !important;margin:0 !important;background:transparent !important;border:0 !important;}'
    '.ec-shell-grouplabel{padding:12px 12px 4px !important;margin:0 !important;'
    'font-size:10.5px !important;font-weight:700 !important;letter-spacing:.06em !important;'
    'text-transform:uppercase !important;color:#9ca3af !important;}'
    'a.ec-shell-item{display:flex !important;align-items:center !important;gap:10px !important;'
    'padding:9px 12px !important;margin:0 !important;border-radius:8px !important;'
    'text-decoration:none !important;font-size:13.5px !important;color:#4b5563 !important;'
    'background:transparent !important;border:0 !important;}'
    'a.ec-shell-item.ec-shell-active{background:#eef0fb !important;color:#2C3DA6 !important;font-weight:600 !important;}'
    '.ec-shell-item svg{width:17px !important;height:17px !important;fill:none !important;'
    'stroke:currentColor !important;stroke-width:1.9 !important;margin:0 !important;}'
    '.ec-shell-foot{border-top:1px solid #e5e7eb !important;padding:10px !important;margin:0 !important;'
    'display:flex !important;align-items:center !important;gap:8px !important;background:transparent !important;}'
    '.ec-shell-topbar{display:flex !important;align-items:center !important;gap:12px !important;'
    'padding:10px 20px !important;margin:0 !important;background:#fff !important;'
    'border:0 !important;border-bottom:1px solid #E5E7F0 !important;position:sticky !important;'
    'top:0 !important;z-index:880 !important;height:auto !important;'
    'font-family:Inter,system-ui,sans-serif !important;font-size:13px !important;}'
    '.ec-shell-crumbs{display:flex !important;align-items:center !important;gap:7px !important;'
    'font-size:13px !important;margin:0 !important;padding:0 !important;}'
    '.ec-shell-tbright{margin-left:auto !important;display:flex !important;align-items:center !important;'
    'gap:6px !important;padding:0 !important;background:transparent !important;border:0 !important;}'
    '.ec-shell-iconbtn{width:32px !important;height:32px !important;border-radius:8px !important;'
    'border:none !important;background:transparent !important;display:flex !important;'
    'align-items:center !important;justify-content:center !important;padding:0 !important;margin:0 !important;}'
    '.ec-shell-iconbtn svg{width:17px !important;height:17px !important;}'
    '</style>')

PAGES = {
    "weekly-update": {"name": "báo-cáo-tuần",
                      "scripts": ("ec-csrf-fetch-patch", "wu-week-nav-js", "ec-chatbot-js")},
    "team-pulse": {"name": "team-pulse",
                   "scripts": ("ec-csrf-fetch-patch", "tp-company-summary-js", "ec-chatbot-js")},
}


def transform(ms, route):
    cfg = PAGES[route]
    for sid in cfg["scripts"]:
        if '<script id="%s"' % sid not in ms:
            raise ValueError("business script missing on %s: %s" % (route, sid))
    if ms.count('data-ec-notification-bell="1"') > 1:
        raise ValueError("unexpected extra bell on %s" % route)
    ms_body = ISOLATION_RE.sub("", ms)
    s0, s1, t0, t1 = boundary.find_window(ms_body)
    # business asides must NOT be inside the replaced window
    for biz in ("wu-roadmap", "tp-ai-panel"):
        i = ms_body.find(biz)
        if i != -1 and s0 <= i < t1:
            raise ValueError("business aside %s inside shell window on %s" % (biz, route))
    new = (ms_body[:s0] + boundary.mount_html("/" + route) + ms_body[s1:t0]
           + boundary.topbar_html("/" + route) + ISOLATION_STYLE + ms_body[t1:])
    boundary.assert_post(new, route,
                         extra_markers=((r'<style id="ec-reporting-shell-isolation">', 1),))
    for sid in cfg["scripts"]:
        if '<script id="%s"' % sid not in new:
            raise ValueError("business script lost on %s: %s" % (route, sid))
    return new


def _sync_one(route):
    name = PAGES[route]["name"]
    if not frappe.db.exists("Web Page", name):
        return {"route": route, "action": "skipped", "reason": "missing"}
    ms = frappe.db.get_value("Web Page", name, "main_section") or ""
    try:
        new = transform(ms, route)
    except ValueError as e:
        frappe.throw(_(str(e)))
    if new == ms:
        return {"route": route, "action": "unchanged"}
    doc = frappe.get_doc("Web Page", name)
    doc.main_section = new
    doc.main_section_html = new
    doc.save(ignore_permissions=True)
    return {"route": route, "action": "updated",
            "len_before": len(ms), "len_after": len(new)}


@frappe.whitelist(methods=["POST"])
def sync_reporting_pages():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync Reporting pages."), frappe.PermissionError)
    return [_sync_one(r) for r in PAGES]

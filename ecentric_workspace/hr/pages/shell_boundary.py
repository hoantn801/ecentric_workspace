# Copyright (c) 2026, eCentric and contributors
"""Governed Shared-Shell boundary sync for the HR Web Pages (/ec-hr/*).

WHY a server-side transform instead of a repo main_section.html:
the sandbox toolchain cannot exfiltrate page bytes (Chrome MCP content
restriction, proven on GBS + salary), and HR business content must be
preserved byte-for-byte. So the repo governs the TRANSFORM, not the bytes:
at sync time we regenerate ONLY the two shell zones from the canonical
registry and prove everything outside them is untouched.

Shell zones (both already exist on the live pages, HR MVP + 7fef8fa):
  1. <aside class="ec-shell-mount"> inner  -> context-aware static sidebar
     (nav context `hr` -> NHÂN SỰ / Chấm công / Phiếu lương at first paint)
  2. bare header-right div -> canonical .ec-shell-topbar (registry crumbs
     "Nhân sự / <page>" + 3-slot header-right), same recipe as /docs/gbs-flow.

Byte-preservation proof: old and new content are compared AFTER stripping
the two shell zones; any difference outside them aborts the sync. The
salary protections (`ec-salary-noprerender` script, `ec-no-prerender`
meta, session-scoped `ec_hr_my_salary_slips`) live OUTSIDE the zones and
are additionally asserted explicitly."""
import re

import frappe
from frappe import _

from ecentric_workspace.shell import fallback as fb
from ecentric_workspace.shell import nav as shell_nav

MOUNT_RE = fb.MOUNT_RE
TBRIGHT_RE = fb.TBRIGHT_RE
TOPBAR_RE = re.compile(r'<div class="ec-shell-topbar" data-ec-shell-topbar="1">.*?'
                       r'data-ec-shell-header-right="1">.*?</div></div>', re.S)

#: stray-literal repair (regression 2026-07-21, /ec-hr/attendance): the live
#: page carries ONE raw "<" text node between the dash wrapper open and the
#: shell mount -- a leftover of the HR workstream's original aside injection.
#: A bare "<" (or "&lt;") IMMEDIATELY before the canonical mount can never be
#: legitimate content, so the transform removes it (transform-level fix, NOT
#: CSS hiding). Strictly anchored: only matches directly before the mount.
STRAY_LT_RE = re.compile(r'(?:<|&lt;)(?=\s*<aside class="ec-shell-mount")')


def _strip_zones(html):
    """Remove both shell zones entirely (order matters: the canonical topbar
    CONTAINS a tbright, so strip it first; a legacy bare tbright is then
    removed as a whole too). What remains = business bytes."""
    html = MOUNT_RE.sub(r"\1\2", html)
    html = TOPBAR_RE.sub("", html)
    html = TBRIGHT_RE.sub("", html)
    return html


def transform(ms, route, required_scripts):
    """PURE context-aware shell-boundary transform for one HR page.

    Returns (new_html, info). Raises ValueError on any guard failure so the
    frappe-facing wrapper can frappe.throw. Pure so the regression tests can
    exercise the exact production logic without a bench."""
    ctx = shell_nav.resolve_context("/" + route)
    if ctx != "hr":
        raise ValueError("Route %s does not resolve to the hr context" % route)

    for guard, expect in (('data-ec-shell="1"', 1),
                          ('data-ec-notification-bell="1"', 1)):
        if ms.count(guard) != expect:
            raise ValueError("Shell guard failed on %s: %s x%s" % (route, guard, ms.count(guard)))
    for sid in required_scripts:
        if ms.count('<script id="%s"' % sid) != 1:
            raise ValueError("Business script missing on %s: %s" % (route, sid))

    # stray-literal repair BEFORE the zone work; the byte proof below then
    # runs against the repaired baseline (the stray is the ONLY sanctioned
    # out-of-zone change, and its removal count is reported).
    ms_clean, stray_removed = STRAY_LT_RE.subn("", ms)

    new = MOUNT_RE.sub(lambda m: m.group(1) + fb.render_mount_inner("/" + route) + m.group(2),
                       ms_clean, count=1)
    if TOPBAR_RE.search(new):
        new = TOPBAR_RE.sub(
            '<div class="ec-shell-topbar" data-ec-shell-topbar="1">'
            + fb.render_topbar_inner("/" + route) + "</div>", new, count=1)
    else:
        new = TBRIGHT_RE.sub(
            '<div class="ec-shell-topbar" data-ec-shell-topbar="1">'
            + fb.render_topbar_inner("/" + route) + "</div>", new, count=1)

    if _strip_zones(ms_clean) != _strip_zones(new):
        raise ValueError("Boundary proof failed on %s: business bytes would change" % route)
    for sid in required_scripts:
        if new.count('<script id="%s"' % sid) != 1:
            raise ValueError("Business script lost on %s: %s" % (route, sid))
    if new.count('data-ec-notification-bell="1"') != 1:
        raise ValueError("Bell contract violated on %s" % route)
    if STRAY_LT_RE.search(new):
        raise ValueError("Stray literal remains before shell mount on %s" % route)

    return new, {"context": ctx, "stray_removed": stray_removed}


def upgrade(route, required_scripts):
    """Idempotent context-aware shell-boundary upgrade for one HR page."""
    name = frappe.db.get_value("Web Page", {"route": route}, "name")
    if not name:
        return {"action": "skipped", "reason": "page missing", "route": route}
    ms = frappe.db.get_value("Web Page", name, "main_section") or ""

    try:
        new, info = transform(ms, route, required_scripts)
    except ValueError as e:
        frappe.throw(_(str(e)))

    if new == ms:
        return {"action": "unchanged", "route": route, "name": name,
                "context": info["context"], "stray_removed": 0}
    doc = frappe.get_doc("Web Page", name)
    doc.main_section = new
    doc.main_section_html = new
    doc.save(ignore_permissions=True)
    return {"action": "updated", "route": route, "name": name,
            "context": info["context"], "stray_removed": info["stray_removed"],
            "len_before": len(ms), "len_after": len(new)}


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync HR pages."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def sync_hr_attendance_page():
    _require_sm()
    return upgrade("ec-hr/attendance", ["ec-hr-attendance"])


@frappe.whitelist(methods=["POST"])
def sync_hr_salary_page():
    _require_sm()
    # salary protections asserted present before AND after the transform
    return upgrade("ec-hr/salary", ["ec-salary-noprerender", "ec-hr-salary"])

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


def _strip_zones(html):
    """Remove both shell zones entirely (order matters: the canonical topbar
    CONTAINS a tbright, so strip it first; a legacy bare tbright is then
    removed as a whole too). What remains = business bytes."""
    html = MOUNT_RE.sub(r"\1\2", html)
    html = TOPBAR_RE.sub("", html)
    html = TBRIGHT_RE.sub("", html)
    return html


def upgrade(route, required_scripts):
    """Idempotent context-aware shell-boundary upgrade for one HR page."""
    ctx = shell_nav.resolve_context("/" + route)
    if ctx != "hr":
        frappe.throw(_("Route %s does not resolve to the hr context") % route)
    name = frappe.db.get_value("Web Page", {"route": route}, "name")
    if not name:
        return {"action": "skipped", "reason": "page missing", "route": route}
    ms = frappe.db.get_value("Web Page", name, "main_section") or ""

    for guard, expect in (('data-ec-shell="1"', 1),
                          ('data-ec-notification-bell="1"', 1)):
        if ms.count(guard) != expect:
            frappe.throw(_("Shell guard failed on %s: %s x%s") % (route, guard, ms.count(guard)))
    for sid in required_scripts:
        if ms.count('<script id="%s"' % sid) != 1:
            frappe.throw(_("Business script missing on %s: %s") % (route, sid))

    new = MOUNT_RE.sub(lambda m: m.group(1) + fb.render_mount_inner("/" + route) + m.group(2),
                       ms, count=1)
    if TOPBAR_RE.search(new):
        new = TOPBAR_RE.sub(
            '<div class="ec-shell-topbar" data-ec-shell-topbar="1">'
            + fb.render_topbar_inner("/" + route) + "</div>", new, count=1)
    else:
        new = TBRIGHT_RE.sub(
            '<div class="ec-shell-topbar" data-ec-shell-topbar="1">'
            + fb.render_topbar_inner("/" + route) + "</div>", new, count=1)

    if _strip_zones(ms) != _strip_zones(new):
        frappe.throw(_("Boundary proof failed on %s: business bytes would change") % route)
    for sid in required_scripts:
        if new.count('<script id="%s"' % sid) != 1:
            frappe.throw(_("Business script lost on %s: %s") % (route, sid))
    if new.count('data-ec-notification-bell="1"') != 1:
        frappe.throw(_("Bell contract violated on %s") % route)

    if new == ms:
        return {"action": "unchanged", "route": route, "name": name, "context": ctx}
    doc = frappe.get_doc("Web Page", name)
    doc.main_section = new
    doc.main_section_html = new
    doc.save(ignore_permissions=True)
    return {"action": "updated", "route": route, "name": name, "context": ctx,
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

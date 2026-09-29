# Copyright (c) 2026, eCentric and contributors
"""Alert Center pages -> Shared Shell (context `alert_center`).

Live topbars are PURE chrome (help icon + raw bell only -- live-verified, no
business controls/ids), so both zones are rebuilt canonically; everything
outside [sidebar..topbar] is reassembled from the ORIGINAL byte slices.

29/09/2026 (brief NHIEU_LOP/brief_alert_center.md): nguon 5 trang da vao repo
(alerts/site_pages/, page_sync co khoa chong troi). `sync_alert_center_pages` gio
dong bo TU REPO thay vi va ban live; `transform` giu lai nhu mot ham thuan cho cac
test Shell (shell/tests/test_module_contexts.py) -- khong con duoc goi tren site."""
import frappe
from frappe import _

from ecentric_workspace.shell import boundary

PAGES = [
    ("alerts", "alert-center"),
    ("alerts/policies", "alert-center-policies"),
    ("alerts/rules", "alert-center-rules"),
    ("alerts/locks", "alert-center-locks"),
    ("alerts/integration-health", "alert-center-integration-health"),
]
REQUIRED_SCRIPTS = ("ec-csrf-fetch-patch", "ec-alert-shared")


def transform(ms, route):
    for sid in REQUIRED_SCRIPTS:
        if '<script id="%s"' % sid not in ms:
            raise ValueError("business script missing on %s: %s" % (route, sid))
    s0, s1, t0, t1 = boundary.find_window(ms)
    new = (ms[:s0] + boundary.mount_html("/" + route) + ms[s1:t0]
           + boundary.topbar_html("/" + route) + ms[t1:])
    boundary.assert_post(new, route)
    for sid in REQUIRED_SCRIPTS:
        if '<script id="%s"' % sid not in new:
            raise ValueError("business script lost on %s: %s" % (route, sid))
    return new


def _sync_one(route, name):
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
def sync_alert_center_pages():
    """Nguon la repo (alerts/site_pages). Ban va live cu (`_sync_one`) doi voi HTML moi se
    tu choi vi khoi <script id="ec-csrf-fetch-patch"> da duoc go - dung goi no nua."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync Alert Center pages."), frappe.PermissionError)
    from ecentric_workspace.alerts.site_pages import sync as site_sync
    return site_sync.sync_all()

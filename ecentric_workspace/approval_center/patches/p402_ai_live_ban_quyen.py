# Copyright (c) 2026, eCentric and contributors
"""p402_ai_live_ban_quyen (17/11/2026): Ban quyen tu dong eLive / eSync / eVoice (Hoan chot 17/11).
- Role "AI Live License Admin" (fixtures cung co; tao truoc o day vi fixtures chay SAU patch) + cap cho user
  dang co System Manager (ho da co quyen cao hon - chi de muc menu "Ban quyen AI Live" hien voi ho).
- Khoi tao EC License Settings: enabled = 1, log_only = 1 (thu tu bat: chay 3-7 ngay chi ghi nhan, thay may live
  bao ve du roi moi tat log_only tren trang). KHONG dong vao khoa - Hoan tu dan.
- Tao Web Page /ai-live/ban-quyen.
Moi buoc tu bat loi, buoc nay loi khong chan buoc kia. Chay lai vo hai (khong ghi de cong tac da doi)."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_live_ban_quyen import page_sync as lic_sync

ROLE = "AI Live License Admin"
SETTINGS = "EC License Settings"


def _role():
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(ignore_permissions=True)
    users = frappe.get_all("Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent")
    for u in sorted(set(users)):
        if u in ("Administrator", "Guest") or not frappe.db.get_value("User", u, "enabled"):
            continue
        if frappe.db.get_value("User", u, "user_type") != "System User":
            continue
        if not frappe.db.exists("Has Role", {"parent": u, "parenttype": "User", "role": ROLE}):
            frappe.get_doc("User", u).add_roles(ROLE)


def _settings():
    if not frappe.db.exists("DocType", SETTINGS):
        return
    if frappe.db.get_single_value(SETTINGS, "teams_format"):
        return                                   # da khoi tao - khong ghi de cong tac Hoan da doi
    doc = frappe.get_single(SETTINGS)
    doc.enabled, doc.log_only, doc.teams_format = 1, 1, "workflows"
    doc.save(ignore_permissions=True)


def execute():
    for name, fn in (("role", _role), ("settings", _settings)):
        try:
            fn()
        except Exception:
            frappe.log_error(title="p402_ai_live_ban_quyen " + name)
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p402_ai_live_ban_quyen page: %s" % (lic_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p402_ai_live_ban_quyen page")

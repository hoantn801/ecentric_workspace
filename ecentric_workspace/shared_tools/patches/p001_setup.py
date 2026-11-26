# Copyright (c) 2026, eCentric and contributors
"""p001: dung nen Kalodata dung chung (27/11/2026).

    1. Role "EC Shared Tool Manager" (chua gan ai - PO gan tren /app/user).
    2. Ban ghi EC Shared Tool "kalodata" voi mac dinh 30 / 3 / 15 / 10 phut. Da co thi GIU NGUYEN.
    3. Dua trang /kalodata len site (shared_tools/pages).
Chay lai bao nhieu lan cung duoc. FAIL-SAFE: loi mot buoc -> Error Log, khong chan migrate.
Can them vao site_config (tay, khong o repo): ec_kalodata_broker_url, ec_kalodata_broker_secret.
"""
import frappe

from ecentric_workspace.shared_tools import constants as C

TITLE = "shared_tools p001 setup"


def execute():
    for step in (_role, _tool, _page):
        try:
            step()
        except Exception:
            frappe.log_error(title="%s: %s" % (TITLE, step.__name__))


def _role():
    if not frappe.db.exists("Role", C.ROLE_MANAGER):
        frappe.get_doc({"doctype": "Role", "role_name": C.ROLE_MANAGER, "desk_access": 1}).insert(
            ignore_permissions=True)


def _tool():
    if not frappe.db.exists("DocType", C.TOOL_DT):
        frappe.reload_doc("shared_tools", "doctype", "ec_shared_tool")
    if frappe.db.exists(C.TOOL_DT, C.TOOL_KALODATA):
        return
    frappe.get_doc({"doctype": C.TOOL_DT, "tool_key": C.TOOL_KALODATA, "title": "Kalodata", "enabled": 1,
                    "lease_minutes": C.DEFAULT_LEASE_MIN, "ready_minutes": C.DEFAULT_READY_MIN,
                    "extend_minutes": C.DEFAULT_EXTEND_MIN, "idle_minutes": C.DEFAULT_IDLE_MIN}).insert(
        ignore_permissions=True)


def _page():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.shared_tools.pages import sync
    frappe.logger("shared_tools").info("p001 pages: %s" % sync.sync_all())

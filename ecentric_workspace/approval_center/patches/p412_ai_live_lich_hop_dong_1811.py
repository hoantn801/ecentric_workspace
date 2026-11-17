# Copyright (c) 2026, eCentric and contributors
"""p412_ai_live_lich_hop_dong_1811 (18/11/2026): Lich live AI tren ERP theo hop dong 18/11 (Hoan chot: bo sung
trang /ai-live co san, giu Nhap -> Phat hanh, them role moi va giu role cu).
- Role "AI Live Scheduler" (nhap + phat hanh lich) va "AI Live Viewer" (chi xem lich). Fixtures cung co; tao truoc o day
  vi fixtures chay SAU patch. KHONG gan role cho ai - System Manager / EC AI Video Admin / EC AI Content van du quyen
  trong code; Hoan tu gan 2 role moi cho nguoi can.
- Khung gio cu: cot `enabled` moi (mac dinh 1) - dat 1 cho dong nao rong (an toan, live hien chua co phien).
- Sync lai Web Page /ai-live (kieu xem Bang / Timeline 06:00 -> 06:00 / Theo brand, bat tat khung, chep tuan co xem truoc).
Moi buoc tu bat loi, buoc nay loi khong chan buoc kia. Chay lai vo hai."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_live import page_sync as live_sync

ROLES = (("AI Live Scheduler", 1), ("AI Live Viewer", 0))
SLOT = "EC AI Live Session Slot"


def _roles():
    for name, desk in ROLES:
        if not frappe.db.exists("Role", name):
            frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": desk}).insert(ignore_permissions=True)


def _slots():
    if frappe.db.has_column(SLOT, "enabled"):
        frappe.db.sql("update `tabEC AI Live Session Slot` set enabled = 1 where enabled is null")


def execute():
    for name, fn in (("roles", _roles), ("slots", _slots)):
        try:
            fn()
        except Exception:
            frappe.log_error(title="p412_ai_live_lich_hop_dong_1811 " + name)
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p412_ai_live_lich_hop_dong_1811 page: %s" % (live_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p412_ai_live_lich_hop_dong_1811 page")

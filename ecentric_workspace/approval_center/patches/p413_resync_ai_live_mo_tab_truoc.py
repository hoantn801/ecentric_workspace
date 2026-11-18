# Copyright (c) 2026, eCentric and contributors
"""p413_resync_ai_live_mo_tab_truoc (18/11/2026): truong "Mo tab truoc gio live (phut)" - lc_open_before_min tren
EC AI Live Session (Int 1..60, trong = theo cai dat tren app). Cot moi do DocType sync tu them (mac dinh trong).
Sua di qua Nhap -> Phat hanh (o "cả phiên" trong hop sua khung cua Lich live); get_config tra o tung phien.
Chi sync lai Web Page /ai-live. Chay lai vo hai."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_live import page_sync as live_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p413_resync_ai_live_mo_tab_truoc: %s" % (live_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p413_resync_ai_live_mo_tab_truoc")

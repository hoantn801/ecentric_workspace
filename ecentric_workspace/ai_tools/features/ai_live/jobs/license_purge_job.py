# Copyright (c) 2026, eCentric and contributors
"""Hang ngay: xoa su kien "bao ve" (checkin) qua 90 ngay. Cap / cho / khoa / thao tac cua nguoi giu mai."""


def run():
    import frappe
    from ecentric_workspace.ai_tools.features.ai_live import license_constants as L
    from ecentric_workspace.ai_tools.features.ai_live.repositories.license_event_repository import LicenseEventRepository
    if not frappe.db.exists("DocType", L.EVENT):
        return
    try:
        LicenseEventRepository().purge_checkins(frappe.utils.add_days(frappe.utils.now_datetime(), -L.EVENT_KEEP_DAYS))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="ai_live license purge")

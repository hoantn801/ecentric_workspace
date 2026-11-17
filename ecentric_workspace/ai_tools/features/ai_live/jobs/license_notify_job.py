# Copyright (c) 2026, eCentric and contributors
"""Job nen: gui Teams "may cho duyet" / "nghi nhan ban" (xep hang tu license_request / license_checkin sau commit)."""


def run(kind=None, machine=None):
    import frappe
    from ecentric_workspace.ai_tools.features.ai_live.application.license_notify_service import LicenseNotifyService
    try:
        LicenseNotifyService().execute(str(kind or ""), str(machine or ""))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="ai_live license notify")

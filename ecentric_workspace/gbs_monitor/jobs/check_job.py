# Copyright (c) 2026, eCentric and contributors
"""Job moi gio (hooks.py scheduler_events hourly)."""

import frappe


def run():
    from ecentric_workspace.gbs_monitor.infrastructure import state
    if state.disabled():
        return
    try:
        from ecentric_workspace.gbs_monitor.application.check_service import CheckBoxmeAccessService
        res = CheckBoxmeAccessService().execute()
        frappe.db.commit()
        if res.get("alerts"):
            frappe.log_error("gbs_monitor %s" % res, "gbs_monitor canh bao")
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "gbs_monitor loi")

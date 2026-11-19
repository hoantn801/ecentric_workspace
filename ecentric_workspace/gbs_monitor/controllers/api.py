# Copyright (c) 2026, eCentric and contributors
"""status(): CHI DOC - System Manager xem IP hien tai + boxme co nhan khoa khong (khong gui thong bao)."""

import frappe


@frappe.whitelist()
def status():
    frappe.only_for("System Manager")
    from ecentric_workspace.gbs_monitor.application.check_service import CheckBoxmeAccessService
    from ecentric_workspace.gbs_monitor.infrastructure import state
    data = CheckBoxmeAccessService().execute(dry_run=True)
    data["saved"] = state.load()
    return {"success": True, "message": "", "data": data}

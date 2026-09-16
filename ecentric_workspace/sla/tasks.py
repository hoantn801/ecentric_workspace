# Copyright (c) 2026, eCentric and contributors
"""Job dinh ky cua module SLA. Chi dieu phoi - logic nam o service.

Moi job o day deu boc try/except toan bo: mot job SLA chet khong duoc lam hong
hang doi scheduler chung cua site (noti, nhac han duyet don, dong bo). Bang diem
van dung neu job nay khong chay - `scoring.effective_status` tinh lai luc doc.
Job chi lam cho DB khop voi su that de Desk/report thay dieu UI thay.
"""
import frappe

from ecentric_workspace.sla.application import obligation_service


def sweep_overdue():
    """Hang gio: danh dau cac dau viec con mo ma da qua han."""
    try:
        res = obligation_service.sweep_overdue()
        if res.get("breached"):
            frappe.logger("sla").info("sweep_overdue: %s" % res)
        return res
    except Exception:
        frappe.log_error(title="sla.tasks.sweep_overdue", message=frappe.get_traceback())
        return None

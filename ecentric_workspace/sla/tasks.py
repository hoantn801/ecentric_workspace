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


def sync_weekly_reports():
    """Hang gio: doc `Weekly Team Update` -> mo/dong nghia vu bao cao tuan.

    CHI DOC ben bao cao tuan, khong sua mot dong nao ben do. Chay lai bao nhieu
    lan cung ra mot ket qua (khoa chong trung la chinh ban bao cao).
    """
    try:
        from ecentric_workspace.sla.infrastructure import weekly_source
        res = weekly_source.sync()
        if res.get("mo") or res.get("dong") or res.get("loi"):
            frappe.logger("sla").info(
                "sync_weekly: quet=%s mo=%s dong=%s khong_han=%s loi=%s"
                % (res.get("quet"), len(res.get("mo") or []), len(res.get("dong") or []),
                   len(res.get("khong_han") or []), len(res.get("loi") or [])))
        return res
    except Exception:
        frappe.log_error(title="sla.tasks.sync_weekly_reports",
                         message=frappe.get_traceback())
        return None


def sync_attendance():
    """Hang ngay: doc `Employee Checkin` -> mo/dong nghia vu ngay cong.

    Cua so mac dinh 7 ngay, khong phai 1: no phai bat duoc ca nguoi cham bu hom
    qua va phieu nghi vua duoc duyet hoi to trong tuan. Chay lai khong nhan doi
    gi - khoa chong trung la (nguoi, ngay).
    """
    try:
        from ecentric_workspace.sla.infrastructure import attendance_source
        res = attendance_source.sync()
        if res.get("hoi_to_nghi_phep") or res.get("loi"):
            frappe.logger("sla").info(
                "sync_attendance: mo=%s dong=%s hoi_to=%s loi=%s"
                % (len(res.get("mo") or []), len(res.get("dong") or []),
                   len(res.get("hoi_to_nghi_phep") or []), len(res.get("loi") or [])))
        return res
    except Exception:
        frappe.log_error(title="sla.tasks.sync_attendance",
                         message=frappe.get_traceback())
        return None

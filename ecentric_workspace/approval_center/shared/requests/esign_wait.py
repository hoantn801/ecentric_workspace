# Copyright (c) 2026, eCentric and contributors
"""Buoc "Duyet & Ky" dang cho cong ky so xac nhan - MOT cua cho moi noi trong Approval Center can biet.

Nguon that DUY NHAT la ban ghi yeu cau ky cua nen tang: `platform.esign.service.in_flight_leg`
(cung ham form DNTT, form 27 p557 dung). Chan ky dang bay o cap HIEN TAI cua phieu -> nguoi duyet da
bam, khong con viec gi; chan ky dung han (Permanent Failure / Cancelled) hoac cap bi tra lai -> khong
con "dang bay" -> phieu hien lai de bam lai.

Dung o (25/11/2026, PO qua chat Ky so):
  * cua so xem nhanh /approvals/all-requests (reporting.actions._apply_esign_wait, p558);
  * tab "Cho toi xu ly" (box=fulfil) + so dem (reporting.queries._my_todo_clause);
  * Viec cua toi / so tren menu "Cho toi duyet" (action_center.feed, source_counts.approval).
Loi nen tang -> Error Log, coi nhu KHONG dang cho (phieu van hien - an nham con te hon hien thua).
"""
import frappe

DSR = "EC Digital Signature Request"


def in_flight(request_name, level_no, user):
    """{status, accepted_at, manual} hoac None."""
    if not (request_name and level_no and user):
        return None
    try:
        from ecentric_workspace.platform.esign import service as esign_service
        leg = esign_service.in_flight_leg(request_name, level_no, user)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "approval_center.esign_wait")
        return None
    if not leg:
        return None
    return {"status": leg.get("status"), "accepted_at": str(leg.get("accepted_at") or ""),
            "manual": leg.get("status") == "Manual Review"}


def waiting_requests(user, levels):
    """`levels` = {ten phieu duyet: cap hien tai}. -> set ten phieu ma `user` dang cho cong xac nhan.

    Loc truoc bang MOT truy van (phieu nao co ban ghi yeu cau ky cua user) roi moi hoi in_flight_leg
    tung phieu con lai - danh sach "cho toi" co the vai chuc phieu, phan lon khong ky so."""
    if not (user and levels):
        return set()
    try:
        if not frappe.db.exists("DocType", DSR):
            return set()
        cand = set(frappe.get_all(DSR, filters={"approval_request": ["in", list(levels)], "approver": user},
                                  pluck="approval_request", ignore_permissions=True) or [])
    except Exception:
        frappe.log_error(frappe.get_traceback(), "approval_center.esign_wait.waiting_requests")
        return set()
    return {name for name in cand if in_flight(name, levels.get(name), user)}

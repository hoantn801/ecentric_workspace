# Copyright (c) 2026, eCentric and contributors
"""Chuyen buoc duyet (vd Ke toan) cho NGUOI KHAC CUNG NHOM (PO 27/11/2026, chi Lien bao: buoc Ke toan cua form
27 dang gui dich danh cho chi, dung ra ke toan khac duyet).

* Cap nao duoc chuyen va chuyen cho ai: routing.HANDOVER_ROLES {ten cap: role} - nguoi nhan = nguoi dang hoat
  dong giu role do, tru nguoi gui va nguoi dang duyet cap do.
* Ai bam duoc: chinh nguoi duyet DANG CHO cua cap do (cap dang mo), hoac System Manager.
* Ghi bang engine.reassign_pending_approver: dong cu -> Skipped, dong moi cung cap, ToDo / thong bao / SLA /
  lich su "Reassigned" (actor that) - KHONG co duong ghi thu hai.
* Dang cho cong ky xac nhan luot "Duyet & Ky" cua nguoi do thi khong chuyen (luot ky gan voi nguoi).
"""
import frappe
from frappe import _

from ecentric_workspace.approval_center.features.contract_review.domain import routing

REQ_DT, LEVEL_DT, APPROVER_DT = "EC Approval Request", "EC Approval Request Level", "EC Approval Request Approver"
DEFAULT_REASON = "Chuyển cho người phụ trách đúng bước này"


def _engine():
    from ecentric_workspace.approval_center.shared.workflow import transitions
    return transitions


def _open_level(request_name):
    """(request, level, role, [dong Pending]) cua cap dang mo neu cap do chuyen duoc, khong thi None."""
    req = frappe.db.get_value(REQ_DT, request_name, ["name", "approval_status", "current_level", "requested_by"],
                              as_dict=True) if request_name else None
    if not req or req.approval_status != "Pending" or not req.current_level:
        return None
    lvl = frappe.db.get_value(LEVEL_DT, {"approval_request": req.name, "level_no": req.current_level},
                              ["name", "level_name", "level_status"], as_dict=True)
    role = routing.HANDOVER_ROLES.get((lvl or {}).get("level_name"))
    if not role or lvl.level_status != "In Progress":
        return None
    rows = frappe.get_all(APPROVER_DT, filters={"approval_request": req.name, "level_no": req.current_level,
                                                "status": "Pending"}, fields=["name", "approver"],
                          order_by="creation asc") or []
    return (req, lvl, role, rows) if rows else None


def _is_sm(user):
    return "System Manager" in frappe.get_roles(user)


def _candidates(req, role, rows):
    eng = _engine()
    taken = {r.approver for r in rows} | {req.requested_by}
    users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent",
                           distinct=True) or []
    out = []
    for u in sorted(set(users)):
        if u not in taken and eng._is_active_system_user(u):
            out.append({"user": u, "full_name": frappe.db.get_value("User", u, "full_name") or u})
    return out


def _mine(rows, user):
    return [r for r in rows if r.approver == user]


def view(business, request, user):
    """Khoi cho trang chi tiet: {"level", "from", "candidates"} khi `user` chuyen duoc, khong thi None."""
    name = (request or {}).get("name") if isinstance(request, dict) else getattr(request, "name", None)
    found = _open_level(name)
    if not found:
        return None
    req, lvl, role, rows = found
    if not (_mine(rows, user) or _is_sm(user)):
        return None
    cands = _candidates(req, role, rows)
    if not cands:
        return None
    from ecentric_workspace.approval_center.shared import vi_display
    return {"level": lvl.level_name, "level_label": vi_display.level_name(lvl.level_name), "level_no": req.current_level,
            "from": [r.approver for r in (_mine(rows, user) or rows)], "candidates": cands}


def handover(name, new_user, reason, user):
    """Chuyen dong duyet dang cho cua `user` (SM: dong dau tien) o cap hien tai sang `new_user`."""
    from ecentric_workspace.approval_center.features.contract_review.application import esign_gate
    request_name = frappe.db.get_value("EC Contract Review Request", name, "approval_request")
    found = _open_level(request_name)
    if not found:
        frappe.throw(_("Bước hiện tại của phiếu không chuyển được cho người khác."))
    req, lvl, role, rows = found
    mine = _mine(rows, user)
    if not (mine or _is_sm(user)):
        frappe.throw(_("Chỉ người đang duyệt bước {0} được chuyển bước này.").format(lvl.level_name),
                     frappe.PermissionError)
    row = (mine or rows)[0]
    if esign_gate.in_flight(frappe.get_doc(REQ_DT, req.name), row.approver):
        frappe.throw(_("Lượt Duyệt & Ký của {0} đang chờ cổng ký xác nhận - chưa chuyển được.").format(row.approver))
    if new_user not in {c["user"] for c in _candidates(req, role, rows)}:
        frappe.throw(_("{0} không nhận được bước này (cần đang hoạt động, giữ vai trò {1}, không phải người gửi "
                       "hay người đang duyệt).").format(new_user, role))
    why = (reason or "").strip()[:300] or DEFAULT_REASON
    res = _engine().reassign_pending_approver(row.name, [new_user], actor=user, reason=why, require_target=True)
    if not res.get("added"):
        frappe.throw(_("Không chuyển được sang {0}.").format(new_user))
    return {"from": row.approver, "to": new_user, "level": lvl.level_name}

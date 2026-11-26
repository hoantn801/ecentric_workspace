# Copyright (c) 2026, eCentric and contributors
"""Noi kho tai san voi cac luong phe duyet DA CO (Approval Center) - mot cua duy nhat.

  * Chuan bi nhan su moi / Asset Request: Ops chon may -> giu cho (truoc ngay onboard) hoac cap
    phat. Voi Asset Request, cap phat xong thi HOAN TAT buoc "Operation xu ly" cua phieu qua chinh
    service cua feature do (khong ghi thang DocType cua module khac). Loi phia phieu -> may van
    duoc cap, tra ve canh bao de Ops hoan tat tay.
  * Clearance: KHONG duyet thay nhom Operation - chi cho biet nguoi nghi con giu gi; thu hoi dung
    service.transition. Ngay lam viec cuoi, job 00:40 tu chuyen may con lai sang Cho kiem tra.
  * Bao hong / mat da duyet: mo phieu sua hoac bao mat, tham chieu phieu goc.
"""
import frappe

from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import lifecycle as L
from ecentric_workspace.tai_san import repair_service as RS
from ecentric_workspace.tai_san import repository as R
from ecentric_workspace.tai_san import service as S

SOURCES = (C.SRC_NSP, C.SRC_ASSET_REQUEST, C.SRC_CLEARANCE, C.SRC_DAMAGE, C.REPAIR_DT)


def allocate(ctx, asset_name, employee, source_type=None, source_name=None, checklist=None,
             note=None, reserve_only=False):
    A.require(ctx.can_manage)
    if source_type and source_type not in SOURCES:
        raise L.TransitionError("Phiếu nguồn không hợp lệ.")
    if not employee and source_type == C.SRC_NSP:
        employee = frappe.db.get_value(C.SRC_NSP, source_name, "new_employee")
    if not employee:
        raise L.TransitionError("Nhân sự mới chưa có hồ sơ nhân viên - giữ chỗ máy trước, cấp phát khi HR tạo hồ sơ.") \
            if source_type == C.SRC_NSP else L.TransitionError("Chọn nhân viên nhận máy.")
    a = R.asset(asset_name)
    action = C.A_RESERVE if reserve_only else C.A_ASSIGN
    res = S.transition(ctx, asset_name, action, employee=employee, ref_doctype=source_type,
                       ref_name=source_name, checklist=_checklist(checklist), note=note)
    if not reserve_only and source_type == C.SRC_ASSET_REQUEST and source_name:
        res["fulfillment"] = _complete_asset_request(ctx, source_name, a, employee, note)
    return res


def reserve_for_nsp(ctx, asset_name, nsp_name, note=None):
    """Giu cho truoc ngay onboard khi nhan su moi CHUA co ho so nhan vien: luu nguoi giu cho la
    chinh Employee neu co, khong thi ghi su kien Reserve tham chieu phieu NSP (board tu an the)."""
    A.require(ctx.can_manage)
    emp = frappe.db.get_value(C.SRC_NSP, nsp_name, "new_employee")
    if emp:
        return allocate(ctx, asset_name, emp, C.SRC_NSP, nsp_name, note=note, reserve_only=True)
    R.lock_asset(asset_name)
    a = R.asset(asset_name)
    L.plan(C.A_RESERVE, a.get(C.OPS_STATUS_FIELD), a.get("custodian"), new_holder="-")
    R.set_asset(asset_name, {C.OPS_STATUS_FIELD: C.ST_RESERVED})
    S.cascade_status(ctx, asset_name, a.get(C.OPS_STATUS_FIELD), C.ST_RESERVED, C.EV_RESERVE,
                     ref_doctype=C.SRC_NSP, ref_name=nsp_name)
    R.insert_event({"asset": asset_name, "event_type": C.EV_RESERVE, "from_status": a.get(C.OPS_STATUS_FIELD),
                    "to_status": C.ST_RESERVED, "ref_doctype": C.SRC_NSP, "ref_name": nsp_name,
                    "note": note or "Giữ chỗ cho nhân sự mới (chưa có hồ sơ nhân viên)", "actor": ctx.user})
    return {"asset": asset_name, "status": C.ST_RESERVED}


def _checklist(items):
    if not items:
        return None
    if isinstance(items, dict):
        return items
    return {str(x): True for x in items}


SP_ASSET_REQUEST = "ts_asset_request"


def _complete_asset_request(ctx, name, asset, employee, note):
    # Savepoint: loi giua chung (claim xong, complete hong) chi huy phan phieu Asset Request -
    # viec cap may van giu, khong de lai phieu nua voi.
    frappe.db.savepoint(SP_ASSET_REQUEST)
    try:
        from ecentric_workspace.approval_center.features.asset_request.application import service as AR
        st = frappe.db.get_value(C.SRC_ASSET_REQUEST, name, ["fulfillment_status", "fulfillment_owner"], as_dict=True)
        if not st or st.fulfillment_status not in C.FULFILL_OPEN:
            return {"ok": False, "message": "Phiếu không còn ở bước Operation xử lý - chỉ ghi nhận cấp phát."}
        if st.fulfillment_status == "Assigned":
            AR.claim_fulfillment(name, user=ctx.user)
        summary = "Cấp phát %s (%s) cho %s qua /tai-san." % (asset.get(C.TAG_FIELD) or asset.name,
                                                            asset.get("asset_name"), employee)
        AR.complete_fulfillment(name, user=ctx.user, payload={
            "fulfillment_summary": summary,
            "asset_handover_note": (summary + (" " + note if note else ""))[:1000]})
        return {"ok": True}
    except Exception as e:
        frappe.db.rollback(save_point=SP_ASSET_REQUEST)
        frappe.log_error(title="tai_san complete asset request %s" % name)
        return {"ok": False, "message": "Đã cấp máy nhưng chưa hoàn tất được phiếu Asset Request: %s. "
                                        "Mở phiếu để hoàn tất tay." % (str(e)[:160])}


def return_for_clearance(ctx, asset_name, clearance, checklist=None, note=None):
    return S.transition(ctx, asset_name, C.A_RETURN, ref_doctype=C.SRC_CLEARANCE, ref_name=clearance,
                        checklist=_checklist(checklist), note=note)


def handle_damage_request(ctx, request_name, asset_name, action, data=None):
    """Phieu Bao hong / mat da duyet -> mo phieu sua (repair) hoac bao mat (lost)."""
    A.require(ctx.can_manage)
    data = dict(data or {})
    if action == "repair":
        data["damage_request"] = request_name
        return RS.open_repair(ctx, asset_name, data)
    if action == "lost":
        return S.transition(ctx, asset_name, C.A_LOST, ref_doctype=C.SRC_DAMAGE, ref_name=request_name,
                            note=data.get("note") or "Theo phiếu báo mất đã duyệt")
    raise L.TransitionError("Chọn: mở phiếu sửa hoặc báo mất.")

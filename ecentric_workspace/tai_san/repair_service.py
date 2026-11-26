# Copyright (c) 2026, eCentric and contributors
"""Sua chua: mo phieu (gui sua), nhan lai, huy. Moi buoc doi trang thai may qua service.transition.

Chi phi du kien > C.REPAIR_APPROVAL_THRESHOLD: KHONG tu gui sua - tra ve need_approval de trang
mo phieu Asset Damage/Loss (luong duyet chi phi da co). Phieu sua mo lai voi damage_request khi
phieu do da duyet.
"""
from frappe.utils import nowdate

from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import lifecycle as L
from ecentric_workspace.tai_san import repository as R
from ecentric_workspace.tai_san import service as S


def open_repair(ctx, asset_name, data):
    A.require(ctx.can_manage)
    level = data.get("damage_level") or C.DAMAGE_PARTIAL
    mode = data.get("repair_mode") or C.MODE_EXTERNAL
    if level not in (C.DAMAGE_PARTIAL, C.DAMAGE_FULL):
        raise L.TransitionError("Mức hỏng phải là Hỏng một phần hoặc Hỏng toàn bộ.")
    if mode not in C.REPAIR_MODES:
        raise L.TransitionError("Hướng xử lý không hợp lệ.")
    a = R.lock_asset(asset_name)  # hai nguoi cung mo phieu sua cho mot may -> nguoi sau thay phieu dang mo
    if R.open_repair_of(asset_name):
        raise L.TransitionError("Thiết bị đang có phiếu sửa chưa đóng.")
    cost = float(data.get("expected_cost") or 0)
    if cost < 0:
        raise L.TransitionError("Chi phí không được âm.")
    if data.get("damage_request"):
        allowed = approved_cost(data["damage_request"], a)
        if R.repairs_using_damage_request(data["damage_request"]):
            raise L.TransitionError("Phiếu %s đã dùng cho một phiếu sửa khác." % data["damage_request"])
        if cost > max(allowed, C.REPAIR_APPROVAL_THRESHOLD):
            raise L.TransitionError("Chi phí dự kiến vượt số đã duyệt trên phiếu %s." % data["damage_request"])
    elif cost > C.REPAIR_APPROVAL_THRESHOLD:
        return {"need_approval": True, "threshold": C.REPAIR_APPROVAL_THRESHOLD,
                "route": C.SOURCE_ROUTES[C.SRC_DAMAGE]}
    parts = data.get("damaged_parts")
    parts = ", ".join(parts) if isinstance(parts, (list, tuple)) else (parts or "")
    loaner = data.get("loaner_asset") or None
    name = R.insert_repair({
        "asset": asset_name, "status": C.REP_IN_REPAIR, "damage_level": level,
        "damaged_parts": parts, "description": data.get("description"), "holder": a.get("custodian"),
        "repair_mode": mode, "vendor": data.get("vendor"), "sent_date": data.get("sent_date") or nowdate(),
        "expected_return": data.get("expected_return"), "expected_cost": cost or None,
        "loaner_asset": loaner, "damage_request": data.get("damage_request"), "note": data.get("note")})
    cond = C.COND_FULL if level == C.DAMAGE_FULL else C.COND_PARTIAL
    S.transition(ctx, asset_name, C.A_REPAIR_START, ref_doctype=C.REPAIR_DT, ref_name=name,
                 condition=cond, note="%s · %s" % (C.REPAIR_MODE_LABELS[mode], data.get("vendor") or "-"),
                 related_asset=loaner)
    if loaner and a.get("custodian"):
        S.transition(ctx, loaner, C.A_ASSIGN, employee=a.get("custodian"), ref_doctype=C.REPAIR_DT,
                     ref_name=name, note="Máy tạm trong lúc sửa " + (a.get(C.TAG_FIELD) or asset_name))
    return {"repair": name}


def norm_code(v):
    """Ma thiet bi tren phieu la chu tu do: so khop nhu bang viec (views._damage_requests)."""
    return str(v or "").strip().upper()


def approved_cost(request_name, asset):
    """Phieu Asset Damage/Loss phai DA DUYET va cua dung may nay. Tra ve chi phi da duyet."""
    req = R.damage_request(request_name)
    if not req or req.approval_status != C.APPROVED:
        raise L.TransitionError("Phiếu %s chưa được duyệt." % request_name)
    if norm_code(req.asset_code) not in {norm_code(asset.get(k)) for k in ("name", C.TAG_FIELD, C.SERIAL_FIELD)
                                         if asset.get(k)}:
        raise L.TransitionError("Phiếu %s không phải của thiết bị này." % request_name)
    return float(req.estimated_repair_cost or 0)


def _lock_repair_and_asset(repair_name):
    """Thu tu khoa CO DINH: may truoc, phieu sau (giong open_repair) - tranh hai giao dich khoa cheo
    nhau (deadlock). Tra ve phieu doc co khoa."""
    R.lock_asset(R.repair(repair_name).asset)
    return R.lock_repair(repair_name)


def close_repair(ctx, repair_name, data):
    A.require(ctx.can_manage)
    rep = _lock_repair_and_asset(repair_name)
    if rep.status not in (C.REP_OPEN, C.REP_IN_REPAIR):
        raise L.TransitionError("Phiếu sửa đã đóng.")
    result = data.get("result")
    if result not in C.REPAIR_RESULTS:
        raise L.TransitionError("Chọn kết quả: sửa được hay không sửa được.")
    actual = float(data.get("actual_cost") or 0)
    if actual < 0:
        raise L.TransitionError("Chi phí không được âm.")
    if actual > C.REPAIR_APPROVAL_THRESHOLD and not ctx.can_finance:
        allowed = approved_cost(rep.damage_request, R.asset(rep.asset)) if rep.damage_request else 0
        if actual > max(allowed, C.REPAIR_APPROVAL_THRESHOLD):
            raise L.TransitionError("Chi phí thực tế trên 3 triệu vượt mức đã duyệt: cần phiếu Asset Damage/Loss "
                                    "đã duyệt đủ số tiền.")
    R.set_repair(repair_name, {"status": C.REP_DONE, "result": result,
                               "returned_date": data.get("returned_date") or nowdate(),
                               "actual_cost": actual,
                               "note": data.get("note") or rep.note})
    if result == C.RES_FIXED:
        cond = data.get("condition") or C.COND_GOOD
        if data.get("return_to") == "stock":
            a = R.lock_asset(rep.asset)
            if a.get("custodian"):
                R.set_asset(rep.asset, {"custodian": None, "department": None})
        S.transition(ctx, rep.asset, C.A_REPAIR_DONE, ref_doctype=C.REPAIR_DT, ref_name=repair_name,
                     condition=cond, note="Sửa xong")  # chi phi o phieu sua (an voi nguoi khong xem chi phi)
    else:
        S.transition(ctx, rep.asset, C.A_REPAIR_FAIL, ref_doctype=C.REPAIR_DT, ref_name=repair_name,
                     condition=C.COND_FULL, note=data.get("note") or "Không sửa được")
    if rep.loaner_asset and result == C.RES_FIXED and data.get("return_to") != "stock":
        loan = R.lock_asset(rep.loaner_asset)
        if loan.get(C.OPS_STATUS_FIELD) == C.ST_IN_USE:
            S.transition(ctx, rep.loaner_asset, C.A_RETURN, ref_doctype=C.REPAIR_DT,
                         ref_name=repair_name, note="Thu máy tạm sau khi sửa xong")
    return {"repair": repair_name, "result": result}


def cancel_repair(ctx, repair_name, note=None):
    A.require(ctx.can_manage)
    rep = _lock_repair_and_asset(repair_name)
    if rep.status not in (C.REP_OPEN, C.REP_IN_REPAIR):
        raise L.TransitionError("Phiếu sửa đã đóng.")
    R.set_repair(repair_name, {"status": C.REP_CANCELLED, "note": note or rep.note})
    a = R.lock_asset(rep.asset)
    if a.get(C.OPS_STATUS_FIELD) == C.ST_UNDER_REPAIR:
        S.transition(ctx, rep.asset, C.A_REPAIR_DONE, ref_doctype=C.REPAIR_DT, ref_name=repair_name,
                     note="Huỷ phiếu sửa")
    return {"repair": repair_name, "cancelled": True}

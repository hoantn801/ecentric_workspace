# Copyright (c) 2026, eCentric and contributors
"""Ban quyen phan mem: nhap, sua, gia han, huy, cap / thu cho cho nhan vien.

Quyen: nguoi quan ly tai san (can_manage) lam moi thao tac; chi phi moi ky nhap luc tao / gia han
(nhu nguyen gia luc nhap thiet bi), sua chi phi sau do chi Finance / HOF. Moi lan cap / thu la mot
dong EC Software License Seat (khong xoa) - do la dau vet cua ban quyen.
"""
import datetime as _dt

from frappe.utils import getdate, nowdate

from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import license_repository as LR
from ecentric_workspace.tai_san import licenses as LIC
from ecentric_workspace.tai_san import lifecycle as L
from ecentric_workspace.tai_san import repository as R
from ecentric_workspace.tai_san import service as S

#: Ten / hang / nhom KHONG sua rieng tren ban quyen - lay theo phan mem (product_service, 27/11/2026).
INFO_FIELDS = ("billing_cycle", "seats", "start_date", "auto_renew",
               "owner_employee", "department", "account", "key_location", "supplier_invoice", "note")
FINANCE_FIELDS = ("cost_per_cycle",)
MAX_SEATS = 10000


def _num(v, label, cast=float):
    try:
        return cast(v or 0)
    except (TypeError, ValueError):
        raise L.TransitionError("%s phải là số." % label)


def _clean(data, ctx, creating):
    v = {}
    for f in INFO_FIELDS:
        if f in data:
            val = data[f]
            v[f] = val.strip()[:140] if isinstance(val, str) and f not in ("note",) else val
            if v[f] == "":
                v[f] = None
    if "cost_per_cycle" in data:
        A.require(creating or ctx.can_finance, "Chỉ Finance / HOF sửa chi phí bản quyền.")
        cost = _num(data.get("cost_per_cycle"), "Chi phí")
        if cost < 0:
            raise L.TransitionError("Chi phí không được âm.")
        v["cost_per_cycle"] = cost or None
    if "seats" in v:
        seats = _num(v["seats"], "Số chỗ", int)
        if seats < 1 or seats > MAX_SEATS:
            raise L.TransitionError("Số chỗ từ 1 đến %d." % MAX_SEATS)
        v["seats"] = seats
    if v.get("billing_cycle") and v["billing_cycle"] not in C.BILLING_CYCLES:
        raise L.TransitionError("Kỳ thanh toán không hợp lệ.")
    if "auto_renew" in v:
        v["auto_renew"] = 1 if str(v["auto_renew"]).lower() in ("1", "true", "yes", "on") else 0
    if v.get("owner_employee"):
        S.require_active_employee(v["owner_employee"])
    if v.get("department") and not LR.department_exists(v["department"]):
        raise L.TransitionError("Không có phòng ban %s." % v["department"])
    if "start_date" in v and not v["start_date"]:
        v.pop("start_date")          # de trong = giu nguyen (dau ky dung de tinh moc nhac)
    if "seats" in data and not v.get("seats"):
        raise L.TransitionError("Số chỗ từ 1 đến %d." % MAX_SEATS)
    return v


def _product_values(product):
    """Ten / hang / nhom cua ban quyen = cua phan mem trong danh muc."""
    if not product:
        raise L.TransitionError("Chọn phần mềm trong danh mục (hoặc Thêm phần mềm mới).")
    p = LR.product(product)
    if p.disabled:
        raise L.TransitionError("Phần mềm %s đang ngừng dùng - chọn phần mềm khác." % p.product_name)
    return p, {"product": p.name, "license_name": p.product_name, "vendor": p.vendor, "category": p.category}


def create(ctx, data):
    A.require(ctx.can_manage, "Chỉ người quản lý tài sản nhập bản quyền.")
    p, pv = _product_values(data.get("product"))
    ltype = data.get("license_type") or p.license_type or C.LT_SUBSCRIPTION
    if ltype not in C.LICENSE_TYPES:
        raise L.TransitionError("Loại bản quyền không hợp lệ.")
    v = _clean(data, ctx, creating=True)
    v.update(pv)
    v.update({"license_type": ltype, "status": C.LS_ACTIVE, "seats": v.get("seats") or 1})
    if ltype == C.LT_SUBSCRIPTION:
        if not data.get("expiry_date"):
            raise L.TransitionError("Thuê bao cần ngày hết hạn.")
        v["billing_cycle"] = v.get("billing_cycle") or p.billing_cycle or C.CY_YEARLY
        v["expiry_date"] = str(getdate(data["expiry_date"]))
        v["start_date"] = v.get("start_date") or nowdate()
        if getdate(v["expiry_date"]) <= getdate(v["start_date"]):
            raise L.TransitionError("Ngày hết hạn phải sau ngày bắt đầu.")
        v["current_term_start"] = v["start_date"]
    else:
        v["billing_cycle"], v["expiry_date"] = None, None
    return {"license": LR.insert_license(v)}


def update(ctx, name, data):
    A.require(ctx.can_manage or ctx.can_finance)
    if any(f in data for f in INFO_FIELDS):
        A.require(ctx.can_manage, "Chỉ người quản lý tài sản sửa thông tin bản quyền.")
    if "product" in data:
        A.require(ctx.can_manage, "Chỉ người quản lý tài sản đổi phần mềm của bản quyền.")
    v = _clean(data, ctx, creating=False)
    if "product" in data:
        v.update(_product_values(data["product"])[1])
    lic = LR.lock_license(name)
    if v.get("start_date") and not LR.renewals(name):
        # Chua gia han lan nao: ngay bat dau chinh la dau ky (moc nhac goi ngan han tinh tu day).
        if lic.expiry_date and getdate(v["start_date"]) >= getdate(lic.expiry_date):
            raise L.TransitionError("Ngày bắt đầu phải trước ngày hết hạn.")
        v["current_term_start"] = v["start_date"]
    if data.get("expiry_date"):
        # Sua han nhap nham (gia han dung `renew`). Doi han -> mo lai moc nhac cho han moi.
        A.require(ctx.can_manage, "Chỉ người quản lý tài sản sửa hạn.")
        if lic.license_type != C.LT_SUBSCRIPTION:
            raise L.TransitionError("Bản quyền vĩnh viễn không có hạn.")
        exp = getdate(data["expiry_date"])
        start = getdate(v.get("start_date") or lic.current_term_start or lic.start_date or nowdate())
        if exp <= start:
            raise L.TransitionError("Ngày hết hạn phải sau đầu kỳ (%s)." % start)
        if str(exp) != str(lic.expiry_date or "")[:10]:
            v.update({"expiry_date": str(exp), "alert_stage": None, "alert_for_expiry": None})
            if lic.status == C.LS_EXPIRED and exp >= getdate(nowdate()):
                v["status"] = C.LS_ACTIVE
    if not v:
        return {"changed": []}
    used = len(LR.lock_active_seats(name)) if "seats" in v else 0
    if "seats" in v and v["seats"] < used:
        raise L.TransitionError("Đang cấp %d chỗ - thu bớt trước khi giảm số chỗ." % used)
    changed = [k for k in v if str(lic.get(k) if lic.get(k) is not None else "")[:140]
               != str(v[k] if v[k] is not None else "")[:140]]
    if not changed:
        return {"changed": []}
    LR.set_license(name, v)
    LR.add_log(name, "Sửa: " + "; ".join("%s: %s → %s" % (k, lic.get(k), v[k]) for k in changed
                                        if k not in ("alert_stage", "alert_for_expiry")), ctx.user)
    return {"changed": changed}


def renew(ctx, name, new_expiry=None, cost=None, note=None):
    """Gia han: han moi phai sau han cu; ghi lich su; mo lai moc nhac cho han moi."""
    A.require(ctx.can_manage, "Chỉ người quản lý tài sản gia hạn bản quyền.")
    lic = LR.lock_license(name)
    if lic.license_type != C.LT_SUBSCRIPTION:
        raise L.TransitionError("Bản quyền vĩnh viễn không cần gia hạn.")
    if lic.status == C.LS_CANCELLED:
        raise L.TransitionError("Bản quyền đã huỷ.")
    if not new_expiry:
        raise L.TransitionError("Chọn hạn mới.")
    new_exp = getdate(new_expiry)
    old_exp = getdate(lic.expiry_date) if lic.expiry_date else None
    if (old_exp and new_exp <= old_exp) or new_exp <= getdate(nowdate()):
        raise L.TransitionError("Hạn mới phải sau hạn cũ và sau hôm nay.")
    cost = _num(cost, "Chi phí") if cost not in (None, "") else None
    if cost is not None and cost < 0:
        raise L.TransitionError("Chi phí không được âm.")
    values = {"expiry_date": str(new_exp), "status": C.LS_ACTIVE, "alert_stage": None, "alert_for_expiry": None,
              "current_term_start": str(old_exp if old_exp and old_exp >= getdate(nowdate()) else getdate(nowdate()))}
    if cost is not None:
        values["cost_per_cycle"] = cost or None
    LR.set_license(name, values)
    LR.add_renewal(name, {"renewed_on": nowdate(), "old_expiry": str(old_exp) if old_exp else None,
                          "new_expiry": str(new_exp), "cost": cost, "renewed_by": ctx.user,
                          "note": (note or "")[:500] or None})
    return {"license": name, "expiry_date": str(new_exp)}


def cancel(ctx, name, note=None):
    """Ngung dung: thu het cho dang cap (giu lich su)."""
    A.require(ctx.can_manage, "Chỉ người quản lý tài sản huỷ bản quyền.")
    lic = LR.lock_license(name)
    if lic.status == C.LS_CANCELLED:
        return {"license": name, "revoked": 0}
    seats = LR.lock_active_seats(name)
    for s in seats:
        LR.revoke_seat(s.name, ctx.user, note="Bản quyền ngừng dùng")
    LR.set_license(name, {"status": C.LS_CANCELLED,
                          "note": ((lic.note or "") + ("\n" if lic.note else "") + "Huỷ: " + (note or ""))[:1000]})
    LR.add_log(name, "Huỷ bản quyền, thu %d chỗ. %s" % (len(seats), note or ""), ctx.user)
    return {"license": name, "revoked": len(seats)}


def assign(ctx, name, employee, note=None):
    A.require(ctx.can_manage, "Chỉ người quản lý tài sản cấp bản quyền.")
    lic = LR.lock_license(name)
    if lic.status != C.LS_ACTIVE or LIC.stage(lic, _today()) == C.STAGE_EXPIRED:
        raise L.TransitionError("Bản quyền đã hết hạn hoặc ngừng dùng - gia hạn trước khi cấp.")
    S.require_active_employee(employee)
    active = LR.lock_active_seats(name)
    if any(s.employee == employee for s in active):
        raise L.TransitionError("Nhân viên này đã có chỗ của bản quyền này.")
    if len(active) >= int(lic.seats or 0):
        raise L.TransitionError("Đã dùng hết %d chỗ - tăng số chỗ hoặc thu lại của người khác." % lic.seats)
    seat = LR.insert_seat({"license": name, "employee": employee, "status": C.SEAT_ACTIVE,
                           "assigned_on": nowdate(), "assigned_by": ctx.user, "note": (note or "")[:500] or None})
    user = R.employee_user(employee)
    if user:
        R.notify([user], "Bạn được cấp bản quyền %s - xem trong Tài sản của tôi." % lic.license_name,
                 "/" + C.ROUTE_MINE)
    return {"seat": seat}


def revoke(ctx, seat_name, note=None):
    A.require(ctx.can_manage, "Chỉ người quản lý tài sản thu bản quyền.")
    LR.lock_license(LR.seat(seat_name).license)
    s = LR.lock_seat(seat_name)
    if s.status != C.SEAT_ACTIVE:
        return {"seat": seat_name, "revoked": False}
    LR.revoke_seat(seat_name, ctx.user, note=note)
    return {"seat": seat_name, "revoked": True}


def revoke_for_leaver(ctx, employee, ref_doctype=None, ref_name=None, last_day=None):
    """Thu moi cho cua nhan vien nghi viec (job dem / thu hoi theo Clearance). Tra ve ten ban quyen."""
    out = []
    for s in LR.active_seats(employees=[employee]):
        LR.revoke_seat(s.name, ctx.user, note="Tự động: nghỉ việc%s" % (" " + str(last_day) if last_day else ""),
                       ref_doctype=ref_doctype, ref_name=ref_name)
        out.append(s.license)
    return out


def _today():
    return _dt.date.fromisoformat(str(nowdate())[:10])

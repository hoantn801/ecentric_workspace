# Copyright (c) 2026, eCentric and contributors
"""Lenh van hanh thiet bi: cap phat, giu cho, thu hoi, kiem tra, dieu chuyen, bao hong, mat,
thanh ly, nhan vien xac nhan / bao hong, sua thong tin.

MOI thay doi trang thai di qua `transition()`: lifecycle.plan quyet dinh, repository ghi, mot dong
EC Asset Event ghi lai (ca cho linh kien dang lap trong may - linh kien di theo may me).
"""
import datetime as _dt

from frappe.utils import getdate, nowdate

from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import lifecycle as L
from ecentric_workspace.tai_san import repository as R

# Truong thong tin nguoi quan ly sua duoc / chi Finance sua duoc (sau khi nhap kho).
INFO_FIELDS = ("asset_name", C.TAG_FIELD, C.SERIAL_FIELD, "ec_condition", "ec_ownership",
               "ec_warranty_until", "ec_supplier", "ec_invoice", "location")
FINANCE_FIELDS = ("net_purchase_amount", "ec_useful_life_months", "ec_depreciation_start",
                  "ec_salvage_value", "purchase_date", "available_for_use_date", "ec_monthly_rent")
#: Truong tien: nhat ky chi ghi "da doi", KHONG ghi gia tri (nhat ky hien cho ca nguoi giu / truong phong).
MONEY_FIELDS = ("net_purchase_amount", "ec_salvage_value", "ec_monthly_rent")


def transition(ctx, asset_name, action, employee=None, ref_doctype=None, ref_name=None,
               note=None, checklist=None, condition=None, related_asset=None):
    A.require(ctx.can_finance if action in L.FINANCE_ACTIONS else ctx.can_manage,
              "Chỉ Finance / HOF được thanh lý." if action in L.FINANCE_ACTIONS else
              "Chỉ người quản lý tài sản được làm thao tác này.")
    R.lock_asset(asset_name)
    a = R.asset(asset_name)
    status = a.get(C.OPS_STATUS_FIELD)
    plan = L.plan(action, status, a.get("custodian"), new_holder=employee,
                  is_component=bool(a.get(C.INSTALLED_ON_FIELD)))
    if action == C.A_RESERVE and not employee:
        raise L.TransitionError("Chọn nhân viên được giữ chỗ.")
    if employee:
        require_active_employee(employee)
    values = _values_for(action, plan, employee, condition, a.get(C.END_DATE_FIELD))
    _apply(ctx, a, action, plan, values, employee=employee, ref_doctype=ref_doctype,
           ref_name=ref_name, note=note, checklist=checklist, condition=condition,
           related_asset=related_asset)
    for comp in R.components_of(asset_name):
        if comp.get(C.OPS_STATUS_FIELD) != status:
            # Du lieu cu: linh kien da lech trang thai voi may me -> khong ghi de (khong hoi sinh
            # linh kien da thanh ly / mat). Can tay: thao ra roi xu ly rieng.
            continue
        _apply(ctx, comp, action, dict(plan, event=plan["event"]), values, employee=employee,
               ref_doctype=ref_doctype, ref_name=ref_name, note="Theo máy mẹ " + asset_name,
               related_asset=asset_name, cascade=True)
    if plan["event"] in (C.EV_ASSIGN, C.EV_TRANSFER) and plan["holder"]:
        user = R.employee_user(plan["holder"])
        if user:
            R.notify([user], "Bạn được cấp thiết bị %s - vào Tài sản của tôi để xác nhận đã nhận."
                     % (a.get(C.TAG_FIELD) or a.name), "/" + C.ROUTE_MINE)
    return {"asset": asset_name, "status": plan["to_status"], "holder": plan["holder"]}


def cascade_status(ctx, parent_name, from_status, to_status, event_type, ref_doctype=None, ref_name=None):
    """Duong doi trang thai may me KHONG qua transition() (bao hong, giu cho NSP) van phai keo linh
    kien dang lap theo - neu khong, lan transition sau se bo qua linh kien (lech trang thai)."""
    for comp in R.components_of(parent_name):
        if comp.get(C.OPS_STATUS_FIELD) != from_status:
            continue
        R.set_asset(comp.name, {C.OPS_STATUS_FIELD: to_status})
        R.insert_event({"asset": comp.name, "event_type": event_type, "from_status": from_status,
                        "to_status": to_status, "from_employee": comp.get("custodian"),
                        "to_employee": comp.get("custodian"), "related_asset": parent_name,
                        "ref_doctype": ref_doctype, "ref_name": ref_name,
                        "note": "Theo máy mẹ " + parent_name, "actor": ctx.user})


def require_active_employee(employee):
    emp = R.employees([employee]).get(employee)
    if not emp or emp.status != "Active":
        raise L.TransitionError("Nhân viên %s không tồn tại hoặc đã nghỉ." % employee)
    return emp


def _values_for(action, plan, employee, condition, end_date=None):
    values = {C.OPS_STATUS_FIELD: plan["to_status"], "custodian": plan["holder"]}
    if plan["holder"]:
        emp = R.employees([plan["holder"]]).get(plan["holder"])
        values["department"] = emp.department if emp else None
    elif plan["holder"] is None and action not in (C.A_RESERVE, C.A_UNRESERVE):
        values["department"] = None
    if action == C.A_RESERVE:
        values[C.RESERVED_FOR_FIELD] = employee
    elif action in (C.A_UNRESERVE, C.A_ASSIGN, C.A_RETURN):
        values[C.RESERVED_FOR_FIELD] = None
    if action in (C.A_LOST, C.A_DISPOSE):
        # Mat thang 3 roi thanh ly thang 6: khau hao dung tu thang 3 - khong doi lich su da chot.
        values[C.END_DATE_FIELD] = end_date or nowdate()
    elif action == C.A_FOUND:
        # Tim thay: khau hao chay tiep; cac thang bi mat duoc chot don vao thang tim thay
        # (jobs.monthly_snapshot lay chenh lech luy ke - so thang luon cong khop).
        values[C.END_DATE_FIELD] = None
    if condition in C.CONDITIONS:
        values["ec_condition"] = condition
    return values


def _apply(ctx, a, action, plan, values, employee=None, ref_doctype=None, ref_name=None, note=None,
           checklist=None, condition=None, related_asset=None, cascade=False):
    vals = dict(values)
    if cascade:
        vals.pop(C.RESERVED_FOR_FIELD, None)
        vals.pop("ec_condition", None)
    R.set_asset(a.name, vals)
    R.insert_event({"asset": a.name, "event_type": plan["event"],
                    "from_status": a.get(C.OPS_STATUS_FIELD), "to_status": plan["to_status"],
                    "from_employee": a.get("custodian"),
                    "to_employee": plan["holder"] if action != C.A_RESERVE else employee,
                    "ref_doctype": ref_doctype, "ref_name": ref_name, "related_asset": related_asset,
                    "condition": vals.get("ec_condition") or a.get("ec_condition"),
                    "checklist": checklist, "note": note, "actor": ctx.user})


# ----------------------------------------------------------- nhan vien ------
def acknowledge(ctx, asset_name):
    A.require(ctx.employee_id, "Tài khoản chưa gắn hồ sơ nhân viên.")
    a = R.asset(asset_name)
    A.require(a.get("custodian") == ctx.employee_id, "Thiết bị này không do bạn giữ.")
    pending = [e for e in R.unacknowledged_events(ctx.employee_id) if e.asset == asset_name]
    if not pending:
        return {"acknowledged": False}
    for e in pending:
        R.set_acknowledged(e.name)
    R.insert_event({"asset": asset_name, "event_type": C.EV_ACK, "to_status": a.get(C.OPS_STATUS_FIELD),
                    "to_employee": ctx.employee_id, "actor": ctx.user, "note": "Nhân viên xác nhận đã nhận đủ."})
    return {"acknowledged": True}


def report_damage(ctx, asset_name, level, parts=None, description=None):
    """Nhan vien bao hong may minh giu. Hong toan bo -> Hong cho xu ly (van giu nguoi giu de Ops
    lien he); hong mot phan -> chi doi tinh trang; mat -> ghi nhan + bao Ops (Ops / phieu
    Asset Damage/Loss moi chuyen Mat)."""
    if level not in C.DAMAGE_LEVELS:
        raise L.TransitionError("Chọn mức hỏng.")
    A.require(ctx.can_manage or ctx.employee_id, "Tài khoản chưa gắn hồ sơ nhân viên.")
    R.lock_asset(asset_name)
    a = R.asset(asset_name)
    A.require(ctx.can_manage or (a.get("custodian") and a.get("custodian") == ctx.employee_id),
              "Thiết bị này không do bạn giữ.")
    if a.get(C.INSTALLED_ON_FIELD):
        raise L.TransitionError("Linh kiện đang lắp trong máy %s: báo hỏng trên máy đó." % a.get(C.INSTALLED_ON_FIELD))
    parts_txt = ", ".join(parts or []) if isinstance(parts, (list, tuple)) else (parts or "")
    note = "Mức: %s. Bộ phận: %s. %s" % (level, parts_txt or "-", (description or "").strip())
    cond = {C.DAMAGE_PARTIAL: C.COND_PARTIAL, C.DAMAGE_FULL: C.COND_FULL}.get(level)
    status = a.get(C.OPS_STATUS_FIELD)
    if level == C.DAMAGE_FULL and status in L.TRANSITIONS[C.A_BREAK][0]:
        R.set_asset(asset_name, {C.OPS_STATUS_FIELD: C.ST_BROKEN, "ec_condition": cond})
        cascade_status(ctx, asset_name, status, C.ST_BROKEN, C.EV_DAMAGE_REPORT)
        new_status = C.ST_BROKEN
    else:
        if cond:
            R.set_asset(asset_name, {"ec_condition": cond})
        new_status = status
    R.insert_event({"asset": asset_name, "event_type": C.EV_DAMAGE_REPORT, "from_status": status,
                    "to_status": new_status, "from_employee": a.get("custodian"),
                    "to_employee": a.get("custodian"), "condition": cond, "note": note[:1000],
                    "actor": ctx.user})
    R.notify_role(C.ROLE_MANAGER, "Báo hỏng %s: %s" % (a.get(C.TAG_FIELD) or asset_name, note[:120]),
                  "/" + C.ROUTE_MOVES)
    return {"asset": asset_name, "status": new_status}


# ----------------------------------------------------------- thong tin ------
def update_info(ctx, asset_name, data):
    A.require(ctx.can_manage or ctx.can_finance)
    values = {}
    for f in INFO_FIELDS:
        if f in data and ctx.can_manage:
            values[f] = data[f] or None
    for f in FINANCE_FIELDS:
        if f in data:
            A.require(ctx.can_finance, "Chỉ Finance / HOF sửa nguyên giá và khấu hao.")
            values[f] = data[f] or None
    if values.get("ec_condition") and values["ec_condition"] not in C.CONDITIONS:
        raise L.TransitionError("Tình trạng không hợp lệ.")
    if values.get("ec_ownership") and values["ec_ownership"] not in C.OWNERSHIPS:
        raise L.TransitionError("Hình thức sở hữu không hợp lệ.")
    if not values:
        return {"changed": []}
    R.lock_asset(asset_name)
    before = R.asset(asset_name)
    validate_money(values.get("net_purchase_amount", before.get("net_purchase_amount")),
                   values.get("ec_useful_life_months", before.get("ec_useful_life_months")),
                   values.get("ec_salvage_value", before.get("ec_salvage_value")))
    R.set_asset(asset_name, values)
    changed = [("%s: đã đổi" % k) if k in MONEY_FIELDS else ("%s: %s → %s" % (k, before.get(k), v))
               for k, v in values.items() if before.get(k) != v]
    if changed:
        R.insert_event({"asset": asset_name, "event_type": C.EV_EDIT,
                        "to_status": before.get(C.OPS_STATUS_FIELD), "note": "; ".join(changed)[:1000],
                        "actor": ctx.user})
    return {"changed": list(values)}


def validate_money(gross, life, salvage=None):
    """Quy tac dung chung cho nhap moi (component_service.create_asset) va sua (update_info)."""
    gross = float(gross or 0)
    if gross < 0 or float(salvage or 0) < 0:
        raise L.TransitionError("Số tiền không được âm.")
    if salvage and float(salvage) > gross:
        raise L.TransitionError("Giá trị thu hồi không lớn hơn nguyên giá.")
    if life in (None, ""):
        return
    life = int(life)
    if life < 1 or life > C.MAX_LIFE_MONTHS:
        raise L.TransitionError("Thời gian khấu hao từ 1 đến %d tháng." % C.MAX_LIFE_MONTHS)
    if life > C.MAX_LIFE_UNDER_THRESHOLD and gross < C.FIXED_ASSET_THRESHOLD:
        raise L.TransitionError("Tài sản dưới 30 triệu là công cụ dụng cụ: phân bổ tối đa 36 tháng.")


def days_until(d):
    return (getdate(d) - _dt.date.today()).days if d else None

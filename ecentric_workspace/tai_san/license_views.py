# Copyright (c) 2026, eCentric and contributors
"""Doc du lieu ban quyen cho trang /tai-san/ban-quyen, Tong quan va Tai san cua toi.

Quyen xem giong thiet bi: nguoi xem chi phi (COST_ROLES) thay het + tien; truong phong chi thay ban
quyen co cho cap cho nhan vien phong minh (va chi cac cho do), khong thay tien; nhan vien thay cho cua
minh o Tai san cua toi.
"""
import datetime as _dt

from frappe.utils import nowdate

from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import license_repository as LR
from ecentric_workspace.tai_san import licenses as LIC
from ecentric_workspace.tai_san import product_service as PS
from ecentric_workspace.tai_san import repository as R

COST_KEYS = ("cost_per_cycle", "monthly_cost", "supplier_invoice")
#: Chi nguoi quan ly tai san: noi luu key, tai khoan quan tri, ghi chu (hay chua gia / thong tin dang nhap).
MANAGER_KEYS = ("account", "key_location", "note")
TODO_LIMIT = 10


def _today():
    return _dt.date.fromisoformat(str(nowdate())[:10])


def _s(v):
    return str(v)[:10] if v else None


def _visible(ctx, lics, seats):
    """(ban quyen nhin thay, cho nhin thay) theo pham vi nguoi xem."""
    scope = ctx.department_scope()
    if scope is None:
        return lics, seats
    emps = R.employees([s.employee for s in seats])
    seats = [s for s in seats if s.employee in emps and emps[s.employee].department in scope]
    keep = {s.license for s in seats}
    return [x for x in lics if x.name in keep or x.department in scope], seats


def _row(ctx, lic, used, today, emps=None):
    st = LIC.stage(lic, today)
    row = {"name": lic.name, "product": lic.product, "license_name": lic.license_name, "vendor": lic.vendor, "category": lic.category,
           "license_type": lic.license_type, "type_label": C.LICENSE_TYPE_LABELS.get(lic.license_type),
           "billing_cycle": lic.billing_cycle, "cycle_label": C.BILLING_CYCLE_LABELS.get(lic.billing_cycle),
           "status": lic.status, "status_label": C.LICENSE_STATUS_LABELS.get(lic.status),
           "seats": int(lic.seats or 0), "used": used, "free": max(int(lic.seats or 0) - used, 0),
           "start_date": _s(lic.start_date), "expiry_date": _s(lic.expiry_date),
           "days_left": LIC.days_left(lic, today), "stage": st, "stage_label": C.STAGE_LABELS.get(st),
           "lead_days": LIC.lead_days(lic), "auto_renew": bool(lic.auto_renew),
           "owner_employee": lic.owner_employee, "department": lic.department, "account": lic.account,
           "key_location": lic.key_location, "note": lic.note,
           "cost_per_cycle": lic.cost_per_cycle, "monthly_cost": LIC.monthly_cost(lic),
           "supplier_invoice": lic.supplier_invoice}
    if emps is not None and lic.owner_employee in emps:
        row["owner_name"] = emps[lic.owner_employee].employee_name
    if not ctx.can_see_cost:
        for k in COST_KEYS:
            row.pop(k)
    if not ctx.can_manage:
        for k in MANAGER_KEYS:
            row.pop(k)
    return row


def _match(row, f):
    stage = f.get("stage")
    if stage == "due" and row["stage"] != C.STAGE_DUE:
        return False
    if stage == "expired" and row["stage"] != C.STAGE_EXPIRED:
        return False
    if stage == "perpetual" and row["license_type"] != C.LT_PERPETUAL:
        return False
    if f.get("status"):
        if row["status"] != f["status"]:
            return False
    elif row["status"] == C.LS_CANCELLED:
        return False
    if f.get("category") and row["category"] != f["category"]:
        return False
    if f.get("product") and row["product"] != f["product"]:
        return False
    q = (f.get("q") or "").strip().lower()
    return not q or q in " ".join(str(row.get(k) or "") for k in
                                  ("name", "license_name", "vendor", "account", "owner_name")).lower()


def summary(ctx, rows):
    live = [r for r in rows if r["status"] != C.LS_CANCELLED]
    out = {"total": len(live), "due": sum(1 for r in live if r["stage"] == C.STAGE_DUE),
           "expired": sum(1 for r in live if r["stage"] == C.STAGE_EXPIRED),
           "seats": sum(r["seats"] for r in live), "used": sum(r["used"] for r in live),
           "perpetual": sum(1 for r in live if r["license_type"] == C.LT_PERPETUAL),
           "cancelled": len(rows) - len(live)}
    if ctx.can_see_cost:
        out["monthly_cost"] = sum(r.get("monthly_cost") or 0 for r in live)
    return out


def groups(ctx, rows):
    """Gop theo phan mem (Hoan: "de sau gop duoc"): moi phan mem mot dong - so lan mua, cho, dang dung,
    han gan nhat, chi phi thang. Ban quyen huy khong tinh."""
    out = {}
    for r in rows:
        if r["status"] == C.LS_CANCELLED:
            continue
        k = r.get("product") or ("~" + (r.get("license_name") or ""))
        g = out.setdefault(k, {"product": r.get("product"), "label": r.get("license_name"), "vendor": r.get("vendor"),
                               "category": r.get("category"), "licenses": 0, "seats": 0, "used": 0,
                               "next_expiry": None, "due": 0, "expired": 0, "monthly_cost": 0})
        g["licenses"] += 1
        g["seats"] += r["seats"]
        g["used"] += r["used"]
        g["due"] += r["stage"] == C.STAGE_DUE
        g["expired"] += r["stage"] == C.STAGE_EXPIRED
        if r.get("expiry_date") and (not g["next_expiry"] or r["expiry_date"] < g["next_expiry"]):
            g["next_expiry"] = r["expiry_date"]
        g["monthly_cost"] += r.get("monthly_cost") or 0
    res = sorted(out.values(), key=lambda g: (g["label"] or "").lower())
    if not ctx.can_see_cost:
        for g in res:
            g.pop("monthly_cost")
    return res


def products_view(ctx):
    """Danh muc cho dropdown (nguoi quan ly) - kem so ban quyen dang tro toi moi phan mem."""
    A.require(ctx.can_overview, "Danh mục phần mềm dành cho quản lý.")
    count = {}
    for x in LR.licenses():
        if x.product and x.status != C.LS_CANCELLED:
            count[x.product] = count.get(x.product, 0) + 1
    rows = [dict(PS.row(p), licenses=count.get(p.name, 0)) for p in LR.products(include_disabled=ctx.can_manage)]
    return {"rows": rows, "categories": list(C.LICENSE_CATEGORIES), "types": C.LICENSE_TYPE_LABELS,
            "cycles": C.BILLING_CYCLE_LABELS, "can": ctx.flags()}


def licenses_view(ctx, filters=None):
    A.require(ctx.can_overview, "Danh sách bản quyền dành cho quản lý.")
    f = filters or {}
    today = _today()
    lics, seats = _visible(ctx, LR.licenses(), LR.active_seats())
    used = {}
    for s in seats:
        used[s.license] = used.get(s.license, 0) + 1
    emps = R.employees([x.owner_employee for x in lics])
    rows = [_row(ctx, x, used.get(x.name, 0), today, emps) for x in lics]
    kept = [r for r in rows if _match(r, f)]
    return {"rows": kept, "groups": groups(ctx, kept), "summary": summary(ctx, rows), "can": ctx.flags(),
            "categories": list(C.LICENSE_CATEGORIES), "cycles": C.BILLING_CYCLE_LABELS,
            "types": C.LICENSE_TYPE_LABELS, "statuses": C.LICENSE_STATUS_LABELS, "stages": C.STAGE_LABELS,
            "lead_days": {"default": C.LICENSE_LEAD_DAYS, "short": C.LICENSE_LEAD_DAYS_SHORT}}


def license_detail(ctx, name):
    A.require(ctx.can_overview, "Chi tiết bản quyền dành cho quản lý.")
    lic = LR.license(name)
    all_seats = LR.seats({"license": name})
    lics, seats = _visible(ctx, [lic], all_seats)
    A.require(bool(lics), "Bạn không xem được bản quyền này.")
    emps = R.employees([s.employee for s in seats] + [lic.owner_employee])
    active = [s for s in seats if s.status == C.SEAT_ACTIVE]
    row = _row(ctx, lic, len([s for s in all_seats if s.status == C.SEAT_ACTIVE]), _today(), emps)
    ren = LR.renewals(name)
    who = LR.user_names([r.renewed_by for r in ren])
    ren = [dict(r, renewed_by_name=who.get(r.renewed_by, r.renewed_by),
                cost=r.cost if ctx.can_see_cost else None,
                note=r.note if ctx.can_manage else None) for r in ren]
    nxt = LIC.next_expiry(lic)

    def seat_row(s):
        e = emps.get(s.employee)
        return {"name": s.name, "employee": s.employee, "employee_name": s.employee_name or (e and e.employee_name),
                "department": e.department if e else None, "status": s.status, "assigned_on": _s(s.assigned_on),
                "revoked_on": _s(s.revoked_on), "note": s.note if ctx.can_manage else None,
                "ref_doctype": s.ref_doctype, "ref_name": s.ref_name}
    return {"license": row, "seats": [seat_row(s) for s in active],
            "history": [seat_row(s) for s in seats if s.status != C.SEAT_ACTIVE][:100],
            "renewals": [dict(r, renewed_on=_s(r.renewed_on), old_expiry=_s(r.old_expiry),
                              new_expiry=_s(r.new_expiry)) for r in ren],
            "suggested_expiry": str(nxt) if nxt else None, "can": ctx.flags()}


def my_licenses(employee_id):
    """Cho dang cap cho nhan vien - KHONG kem tien."""
    if not employee_id:
        return []
    seats = LR.active_seats(employees=[employee_id])
    if not seats:
        return []
    today = _today()
    by = {x.name: x for x in LR.licenses({"name": ["in", [s.license for s in seats]]})}
    out = []
    for s in seats:
        lic = by.get(s.license)
        if not lic:
            continue
        st = LIC.stage(lic, today)
        out.append({"seat": s.name, "license": lic.name, "license_name": lic.license_name, "vendor": lic.vendor,
                    "category": lic.category, "type_label": C.LICENSE_TYPE_LABELS.get(lic.license_type),
                    "expiry_date": _s(lic.expiry_date),
                    "days_left": LIC.days_left(lic, today), "stage": st, "stage_label": C.STAGE_LABELS.get(st),
                    "assigned_on": _s(s.assigned_on)})
    return out


def held_by(employee_ids):
    """{employee: [ten ban quyen dang giu]} - cho bang thu hoi nghi viec."""
    seats = LR.active_seats(employees=employee_ids)
    names = {x.name: x.license_name for x in LR.licenses({"name": ["in", list({s.license for s in seats}) or [""]]})}
    out = {}
    for s in seats:
        out.setdefault(s.employee, []).append({"seat": s.name, "license": s.license,
                                               "license_name": names.get(s.license, s.license)})
    return out


def dashboard_block(ctx):
    """Khoi Ban quyen tren Tong quan: so lieu + danh sach can xu ly (sap het / qua han)."""
    today = _today()
    lics, seats = _visible(ctx, LR.licenses(), LR.active_seats())
    used = {}
    for s in seats:
        used[s.license] = used.get(s.license, 0) + 1
    rows = [_row(ctx, x, used.get(x.name, 0), today) for x in lics]
    todo = sorted([r for r in rows if r["status"] != C.LS_CANCELLED and r["stage"] in (C.STAGE_DUE, C.STAGE_EXPIRED)],
                  key=lambda r: r["days_left"])[:TODO_LIMIT]
    return {"summary": summary(ctx, rows), "todo": todo}

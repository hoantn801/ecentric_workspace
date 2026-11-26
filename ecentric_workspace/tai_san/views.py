# Copyright (c) 2026, eCentric and contributors
"""Doc du lieu cho cac trang /tai-san (Tong quan, Danh sach, Chi tiet, Tai san cua toi, Luan
chuyen, Sua chua). Moi ham nhan Ctx, LOC theo quyen o day (gia chi tra ve khi can_see_cost)."""
import json

from frappe.utils import add_days, getdate, nowdate

from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import count_service as KK
from ecentric_workspace.tai_san import depreciation as D
from ecentric_workspace.tai_san import domain as DOM
from ecentric_workspace.tai_san import lifecycle as L
from ecentric_workspace.tai_san import reports as RP
from ecentric_workspace.tai_san import repository as R

PAGE_SIZE = 50


def _today():
    return getdate(nowdate())


def _scoped(ctx, assets):
    scope = ctx.department_scope()
    if scope is None:
        return assets
    return [a for a in assets if a.get("department") in scope]


def _row(ctx, a, cats, emps, comp_count=None):
    life = (cats.get(a.get("asset_category")) or {}).get("ec_default_life_months")
    holder = emps.get(a.get("custodian")) if a.get("custodian") else None
    status = a.get(C.OPS_STATUS_FIELD)
    out = {"name": a["name"], "tag": a.get(C.TAG_FIELD), "asset_name": a.get("asset_name"),
           "category": a.get("asset_category"), "status": status,
           "status_label": C.STATUS_LABELS.get(status, status or ""),
           "condition": a.get("ec_condition") or C.COND_GOOD, "serial": a.get(C.SERIAL_FIELD),
           "holder": a.get("custodian"), "holder_name": holder.employee_name if holder else None,
           "holder_left": bool(holder and holder.status == "Left"),
           "department": a.get("department"), "purchase_date": _s(a.get("purchase_date")),
           "warranty_until": _s(a.get("ec_warranty_until")), "ownership": a.get("ec_ownership"),
           "installed_on": a.get(C.INSTALLED_ON_FIELD), "components": comp_count or 0,
           "reserved_for": a.get(C.RESERVED_FOR_FIELD)}
    if ctx.can_see_cost:
        d = D.compute(a, life, _today())
        out.update({"gross": d["gross"], "nbv": d["nbv"], "accumulated": d["accumulated"],
                    "monthly": d["monthly"], "months_done": d["months_done"], "life": d["life"]})
    return out


def _s(v):
    return str(v)[:10] if v else None


def _base(ctx):
    assets = R.assets()
    cats = R.categories()
    emps = R.employees([a.get("custodian") for a in assets] + [a.get(C.RESERVED_FOR_FIELD) for a in assets])
    comp = {}
    for a in assets:
        if a.get(C.INSTALLED_ON_FIELD):
            comp[a.get(C.INSTALLED_ON_FIELD)] = comp.get(a.get(C.INSTALLED_ON_FIELD), 0) + 1
    return assets, cats, emps, comp


# ------------------------------------------------------------------ Tong quan --
def dashboard(ctx, month=None, department=None, category=None):
    A.require(ctx.can_overview, "Tổng quan tài sản dành cho quản lý.")
    assets, cats, emps, comp = _base(ctx)
    assets = _scoped(ctx, assets)
    if department:
        assets = [a for a in assets if (a.get("department") or C.STOCK_BUCKET) == department]
    if category:
        assets = [a for a in assets if a.get("asset_category") == category]
    as_of = D.month_key(month) if month else D.month_key(_today())
    out = {"kpis": RP.kpis(assets), "by_category": RP.by_category(assets),
           "by_department": RP.by_department(assets, cats, as_of, ctx.can_see_cost),
           "age": RP.age_buckets(assets, as_of), "month": D.month_str(as_of),
           "status_labels": C.STATUS_LABELS, "can": ctx.flags(),
           "filters": {"departments": sorted({a.get("department") or C.STOCK_BUCKET for a in assets}),
                       "categories": sorted(cats)}}
    if ctx.can_see_cost:
        since = D.month_str(D.add_months(as_of, -11)) + "-01"
        rep = R.repair_cost_by_month(since)
        out["finance"] = RP.finance(assets, cats, as_of, rep)
        out["cost_12m"] = RP.cost_series(assets, cats, as_of, rep)
    out["todo"] = _todo(ctx, assets, cats, emps)
    return out


def _todo(ctx, assets, cats, emps):
    today = _today()
    by_holder = {}
    for a in assets:
        if a.get("custodian") and not a.get(C.INSTALLED_ON_FIELD):
            by_holder.setdefault(a.get("custodian"), []).append(a)
    returns = []
    scope = ctx.department_scope()
    for c in R.clearances_upcoming(add_days(today, -7), add_days(today, C.RETURN_HORIZON_DAYS)):
        if scope is not None and c.department not in scope:
            continue
        held = by_holder.get(c.employee, [])
        returns.append({"source": c.name, "route": _route(C.SRC_CLEARANCE, c.name),
                        "employee": c.employee, "employee_name": c.employee_name,
                        "department": c.department, "last_working_day": _s(c.last_working_day),
                        "days_left": (getdate(c.last_working_day) - today).days,
                        "assets": [{"name": a["name"], "tag": a.get(C.TAG_FIELD),
                                    "asset_name": a.get("asset_name")} for a in held]})
    left = [{"asset": a["name"], "tag": a.get(C.TAG_FIELD), "asset_name": a.get("asset_name"),
             "employee": a.get("custodian"), "employee_name": emps[a.get("custodian")].employee_name}
            for a in assets if a.get("custodian") in emps and emps[a.get("custodian")].status == "Left"
            and a.get(C.OPS_STATUS_FIELD) == C.ST_IN_USE]
    allocations = [x for x in _allocations(today) if scope is None or x.get("department") in scope]
    # assets da qua _scoped(): truong phong chi thay sua chua / nghi viec / nhan su moi cua phong minh.
    in_scope = {a["name"]: a for a in assets}
    repairs = [_repair_row(ctx, r, in_scope) for r in
               R.repairs({"status": ["in", [C.REP_OPEN, C.REP_IN_REPAIR]]}) if r.asset in in_scope]
    names = {a["name"]: a for a in assets}
    warranty = [dict(w, tag=names[w["asset"]].get(C.TAG_FIELD), asset_name=names[w["asset"]].get("asset_name"))
                for w in RP.warranty_alerts(assets, today)]
    out = {"returns": returns, "holder_left": left, "allocations": allocations, "repairs": repairs,
           "warranty": warranty}
    if ctx.can_see_cost:
        out["fully_depreciated"] = [{"asset": n, "tag": names[n].get(C.TAG_FIELD),
                                     "asset_name": names[n].get("asset_name")}
                                    for n in RP.fully_depreciated_in_use(assets, cats, today)]
    last = R.last_event_time([a["name"] for a in assets if a.get(C.OPS_STATUS_FIELD) == C.ST_AVAILABLE], C.EV_RETURN)
    out["idle"] = [dict(i, tag=names[i["asset"]].get(C.TAG_FIELD), asset_name=names[i["asset"]].get("asset_name"))
                   for i in RP.idle_assets(assets, last, today)][:10]
    return out


def _route(dt, name):
    return "%s?id=%s" % (C.SOURCE_ROUTES[dt], name)


def _allocations(today):
    out = []
    nsp = R.nsp_upcoming(add_days(today, -7), add_days(today, C.ONBOARD_HORIZON_DAYS))
    evs = R.events_for_refs(C.SRC_NSP, [n.name for n in nsp])
    done = {e.ref_name for e in evs if e.event_type == C.EV_ASSIGN}
    held = {}
    for e in sorted(evs, key=lambda x: x.event_time):
        if e.event_type == C.EV_RESERVE:
            held[e.ref_name] = e.asset
        elif e.event_type == C.EV_UNRESERVE:
            held.pop(e.ref_name, None)
    for n in nsp:
        if n.name in done:
            continue
        ra = held.get(n.name)
        if ra and R.asset(ra).get(C.OPS_STATUS_FIELD) != C.ST_RESERVED:
            ra = None
        out.append({"source": n.name, "source_type": C.SRC_NSP, "source_label": C.SOURCE_LABELS[C.SRC_NSP],
                    "route": _route(C.SRC_NSP, n.name), "employee": n.new_employee,
                    "employee_name": n.candidate_name, "department": n.department,
                    "need": "Laptop · " + (n.position or ""), "due": _s(n.onboard_date),
                    "reserved_asset": ra, "has_employee": bool(n.new_employee)})
    reqs = [r for r in R.asset_requests_to_fulfil() if r.request_type == "Request new asset"]
    done = {e.ref_name for e in R.events_for_refs(C.SRC_ASSET_REQUEST, [r.name for r in reqs])
            if e.event_type == C.EV_ASSIGN}
    for r in reqs:
        if r.name in done:
            continue
        out.append({"source": r.name, "source_type": C.SRC_ASSET_REQUEST,
                    "source_label": C.SOURCE_LABELS[C.SRC_ASSET_REQUEST],
                    "route": _route(C.SRC_ASSET_REQUEST, r.name), "employee": r.employee,
                    "employee_name": r.request_title, "department": r.department,
                    "need": "%s × %s · %s" % (r.asset_type or "", r.quantity or 1, (r.specifications or "")[:80]),
                    "due": _s(r.requested_needed_date)})
    return out


COST_KEYS = ("expected_cost", "actual_cost")
#: Van de du lieu lo gia tri tien - chi nguoi xem duoc chi phi moi thay.
COST_ISSUES = (C.ISSUE_COMPONENT_PRICE, C.ISSUE_NO_PRICE)


def _repair_row(ctx, r, by_name):
    a = by_name.get(r.asset) or {}
    late = bool(r.expected_return and r.status == C.REP_IN_REPAIR and getdate(r.expected_return) < _today())
    out = {"name": r.name, "asset": r.asset, "tag": a.get(C.TAG_FIELD), "asset_name": a.get("asset_name"),
            "status": r.status, "status_label": C.REPAIR_STATUS_LABELS.get(r.status),
            "damage_level": r.damage_level, "damaged_parts": r.damaged_parts, "mode": r.repair_mode,
            "mode_label": C.REPAIR_MODE_LABELS.get(r.repair_mode), "vendor": r.vendor,
            "sent_date": _s(r.sent_date), "expected_return": _s(r.expected_return),
            "returned_date": _s(r.returned_date), "expected_cost": r.expected_cost,
            "actual_cost": r.actual_cost, "result": r.result, "loaner_asset": r.loaner_asset,
            "overdue": late}
    if not ctx.can_see_cost:
        for k in COST_KEYS:
            out.pop(k)
    return out


# ------------------------------------------------------------------ Danh sach --
def list_assets(ctx, filters=None):
    filters = filters or {}
    A.require(ctx.can_overview, "Danh sách thiết bị dành cho quản lý.")
    assets, cats, emps, comp = _base(ctx)
    rows = [_row(ctx, a, cats, emps, comp.get(a["name"])) for a in _scoped(ctx, assets)]
    issues = DOM.audit_assets(assets, {e: emps[e].status for e in emps})
    for r in rows:
        r["issues"] = [C.ISSUE_LABELS[i] for i in issues.get(r["name"], [])
                       if ctx.can_see_cost or i not in COST_ISSUES]
    rows = _filter_rows(rows, filters)
    page = max(int(filters.get("page") or 1), 1)
    return {"rows": rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE], "total": len(rows), "page": page,
            "page_size": PAGE_SIZE, "can": ctx.flags(), "status_labels": C.STATUS_LABELS,
            "categories": sorted(cats), "departments": sorted({r["department"] for r in rows if r["department"]})}


def _filter_rows(rows, f):
    q = (f.get("q") or "").strip().lower()
    out = []
    for r in rows:
        if f.get("status") and r["status"] != f["status"]:
            continue
        if f.get("category") and r["category"] != f["category"]:
            continue
        if f.get("department") and (r["department"] or C.STOCK_BUCKET) != f["department"]:
            continue
        if f.get("holder") and r["holder"] != f["holder"]:
            continue
        if f.get("issues_only") and not r.get("issues"):
            continue
        if not f.get("include_components") and r["installed_on"]:
            continue
        if q and q not in " ".join(str(r.get(k) or "") for k in
                                   ("tag", "asset_name", "serial", "holder_name", "name")).lower():
            continue
        out.append(r)
    return out


# ------------------------------------------------------------------ Chi tiet --
def asset_detail(ctx, name):
    a = R.asset(name)
    A.require(ctx.can_view_asset(a), "Bạn không xem được thiết bị này.")
    cats = R.categories()
    comps = R.components_of(name)
    emps = R.employees([a.get("custodian"), a.get(C.RESERVED_FOR_FIELD)] +
                       [e.from_employee for e in R.events(name)] + [e.to_employee for e in R.events(name)])
    row = _row(ctx, a, cats, emps, len(comps))
    life = (cats.get(a.get("asset_category")) or {}).get("ec_default_life_months")
    out = {"asset": row, "specs": R.specs(name),
           "spec_template": _spec_template(cats, a.get("asset_category")),
           "components": [_row(ctx, c, cats, emps) for c in comps],
           "parent": _row(ctx, R.asset(a.get(C.INSTALLED_ON_FIELD)), cats, emps) if a.get(C.INSTALLED_ON_FIELD) else None,
           "events": [_event_row(e, emps) for e in R.events(name)],
           "repairs": [_repair_row(ctx, r, {name: a}) for r in R.repairs({"asset": name})],
           "actions": [{"action": x, "label": C.ACTION_LABELS[x]} for x in L.allowed_actions(a.get(C.OPS_STATUS_FIELD))]
           if ctx.can_manage else [], "can": ctx.flags(),
           "is_component_category": bool((cats.get(a.get("asset_category")) or {}).get("ec_is_component"))}
    if ctx.can_see_cost:
        d = D.compute(a, life, _today())
        d["curve"] = D.nbv_curve(a, life, points=24)
        d["components_total"] = sum(float(c.get("net_purchase_amount") or 0) for c in comps)
        out["depreciation"] = d
        out["info"] = {k: _s(a.get(k)) if "date" in k or "until" in k or "start" in k else a.get(k)
                       for k in ("ec_ownership", "ec_monthly_rent", "ec_supplier", "ec_invoice",
                                 "ec_useful_life_months", "ec_depreciation_start", "ec_salvage_value",
                                 "available_for_use_date", "location", "item_code")}
    return out


def _spec_template(cats, category):
    raw = (cats.get(category) or {}).get("ec_spec_template")
    if not raw:
        d = DOM.category_defaults(category)
        raw = d[2] if d else ""
    return [s.strip() for s in raw.split(",") if s.strip()]


def _event_row(e, emps):
    def nm(x):
        return emps[x].employee_name if x in emps else x
    try:
        checklist = json.loads(e.checklist) if e.checklist else None
    except ValueError:
        checklist = None
    return {"type": e.event_type, "label": C.EVENT_LABELS.get(e.event_type, e.event_type),
            "time": str(e.event_time)[:16], "actor": e.actor, "from_status": e.from_status,
            "to_status": e.to_status, "from_employee": nm(e.from_employee), "to_employee": nm(e.to_employee),
            "ref_doctype": e.ref_doctype, "ref_name": e.ref_name,
            "ref_route": _route(e.ref_doctype, e.ref_name) if e.ref_doctype in C.SOURCE_ROUTES and e.ref_name else None,
            "related_asset": e.related_asset, "note": e.note, "checklist": checklist,
            "acknowledged_at": str(e.acknowledged_at)[:16] if e.acknowledged_at else None}


# ----------------------------------------------------------- Tai san cua toi --
def my_assets(ctx):
    if not ctx.employee_id:
        return {"assets": [], "no_employee": True, "can": ctx.flags()}
    cats = R.categories()
    mine = R.assets({"custodian": ctx.employee_id})
    pending = {e.asset for e in R.unacknowledged_events(ctx.employee_id)}
    emps = R.employees([ctx.employee_id])
    rows = []
    for a in mine:
        r = _row(A.Ctx(ctx.user, []), a, cats, emps)
        r["pending_ack"] = a["name"] in pending
        r["specs"] = R.specs(a["name"])
        r["components"] = [{"name": c["name"], "tag": c.get(C.TAG_FIELD), "asset_name": c.get("asset_name")}
                           for c in R.components_of(a["name"])]
        if not a.get(C.INSTALLED_ON_FIELD):
            rows.append(r)
    count = R.open_count()
    confirmed = KK.my_confirmations(ctx.employee_id) if count else {}
    for r in rows:
        r["count_confirmed"] = confirmed.get(r["name"])
    return {"assets": rows, "employee": ctx.employee, "can": ctx.flags(),
            "damage_levels": C.DAMAGE_LEVELS, "count": dict(count) if count else None,
            "request_route": C.SOURCE_ROUTES[C.SRC_ASSET_REQUEST]}


# -------------------------------------------------------------- Luan chuyen --
def board(ctx):
    A.require(ctx.can_manage, "Trang cấp phát & thu hồi dành cho người quản lý tài sản.")
    assets, cats, emps, comp = _base(ctx)
    today = _today()
    allocate = _allocations(today)
    reserved = [_row(ctx, a, cats, emps) for a in assets if a.get(C.OPS_STATUS_FIELD) == C.ST_RESERVED]
    by_holder = {}
    for a in assets:
        if a.get("custodian") and not a.get(C.INSTALLED_ON_FIELD):
            by_holder.setdefault(a.get("custodian"), []).append(a)
    returns = []
    for c in R.clearances_upcoming(add_days(today, -14), add_days(today, C.RETURN_HORIZON_DAYS)):
        held = by_holder.get(c.employee, [])
        returns.append({"source": c.name, "route": _route(C.SRC_CLEARANCE, c.name), "employee": c.employee,
                        "employee_name": c.employee_name, "department": c.department,
                        "last_working_day": _s(c.last_working_day),
                        "days_left": (getdate(c.last_working_day) - today).days,
                        "assets": [_row(ctx, a, cats, emps) for a in held], "all_returned": not held})
    checks = [_row(ctx, a, cats, emps) for a in assets if a.get(C.OPS_STATUS_FIELD) == C.ST_PENDING_CHECK
              and not a.get(C.INSTALLED_ON_FIELD)]
    broken = [_row(ctx, a, cats, emps) for a in assets if a.get(C.OPS_STATUS_FIELD) == C.ST_BROKEN
              and not a.get(C.INSTALLED_ON_FIELD)]
    by_name = {a["name"]: a for a in assets}
    repairs = [_repair_row(ctx, r, by_name) for r in R.repairs({"status": ["in", [C.REP_OPEN, C.REP_IN_REPAIR]]})]
    damage = _damage_requests(assets)
    return {"allocate": allocate, "reserved": reserved, "returns": returns, "checks": checks,
            "broken": broken, "repairs": repairs, "damage_requests": damage,
            "handover_checklist": C.HANDOVER_CHECKLIST, "return_checklist": C.RETURN_CHECKLIST,
            "repair_threshold": C.REPAIR_APPROVAL_THRESHOLD, "can": ctx.flags()}


def _damage_requests(assets):
    """Phieu Bao hong / mat DA DUYET chua co phieu sua / su kien mat tro toi. Doan thiet bi tu
    asset_code (tag / ma he thong / serial) - truong nay la chu tu do tren phieu."""
    reqs = R.damage_requests_approved(add_days(_today(), -180))
    handled = {r.damage_request for r in R.repairs({"damage_request": ["is", "set"]})}
    handled |= {e.ref_name for e in R.events_for_refs(C.SRC_DAMAGE, [r.name for r in reqs])}
    index = {}
    for a in assets:
        for k in (a.get(C.TAG_FIELD), a["name"], a.get(C.SERIAL_FIELD)):
            if k:
                index[str(k).strip().upper()] = a
    out = []
    for r in reqs:
        if r.name in handled:
            continue
        hit = index.get((r.asset_code or "").strip().upper())
        out.append({"source": r.name, "route": _route(C.SRC_DAMAGE, r.name), "title": r.request_title,
                    "incident_type": r.incident_type, "incident_date": _s(r.incident_date),
                    "asset_code": r.asset_code, "asset": hit["name"] if hit else None,
                    "tag": hit.get(C.TAG_FIELD) if hit else None,
                    "estimated_cost": r.estimated_repair_cost})
    return out


# ------------------------------------------------------------------ Sua chua --
def repairs_view(ctx, status=None):
    A.require(ctx.can_manage or ctx.can_see_cost)
    by_name = {a["name"]: a for a in R.assets()}
    flt = {"status": status} if status else {}
    rows = [_repair_row(ctx, r, by_name) for r in R.repairs(flt, limit=500)]
    since = D.month_str(D.add_months(D.month_key(_today()), -11)) + "-01"
    return {"rows": rows, "cost_by_month": R.repair_cost_by_month(since) if ctx.can_see_cost else None,
            "repeat": {k: v for k, v in R.repair_count_by_asset().items() if v >= C.REPEAT_REPAIR_COUNT},
            "status_labels": C.REPAIR_STATUS_LABELS, "mode_labels": C.REPAIR_MODE_LABELS, "can": ctx.flags()}


# -------------------------------------------------------------------- chon --
def pickers(ctx, kind, category=None):
    A.require(ctx.can_manage)
    if kind == "employees":
        return [{"name": e.name, "label": e.employee_name, "department": e.department}
                for e in R.active_employees()]
    if kind == "items":
        return [{"name": i.name, "label": i.item_name, "category": i.asset_category}
                for i in R.fixed_asset_items()]
    assets, cats, emps, comp = _base(ctx)
    if kind == "available":
        rows = [a for a in assets if a.get(C.OPS_STATUS_FIELD) in (C.ST_AVAILABLE, C.ST_RESERVED)
                and not a.get(C.INSTALLED_ON_FIELD)
                and not (cats.get(a.get("asset_category")) or {}).get("ec_is_component")]
    elif kind == "components":
        rows = [a for a in assets if (cats.get(a.get("asset_category")) or {}).get("ec_is_component")
                and not a.get(C.INSTALLED_ON_FIELD) and a.get(C.OPS_STATUS_FIELD) == C.ST_AVAILABLE]
    else:
        raise A.AccessDenied("Danh sách không hợp lệ.")
    if category:
        rows = [a for a in rows if a.get("asset_category") == category]
    out = []
    for a in rows:
        r = _row(ctx, a, cats, emps)
        r["specs"] = "; ".join("%s %s" % (s.part_type, s.spec) for s in R.specs(a["name"]))
        out.append(r)
    return out


def audit(ctx):
    A.require(ctx.can_manage or ctx.can_see_cost)
    assets, cats, emps, comp = _base(ctx)
    issues = DOM.audit_assets(assets, {e: emps[e].status for e in emps})
    rows = [dict(_row(ctx, a, cats, emps), issues=[C.ISSUE_LABELS[i] for i in issues[a["name"]]])
            for a in assets if a["name"] in issues]
    return {"rows": rows, "total": len(rows)}


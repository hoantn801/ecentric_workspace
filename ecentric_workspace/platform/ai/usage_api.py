# Copyright (c) 2026, eCentric and contributors
"""Trang /ai-usage - so lieu dung AI cua nhan su (Hoan 07/10).

AI XEM DUOC GI (Hoan chon "Ban lanh dao + quan ly phong"):
  * Toan cong ty : System Manager, EC CEO, hoac role `EC AI Usage Viewer` (gan them ai can).
  * Truong phong : Department co `manager_email` = minh -> nhan su cua (cac) phong do + chinh minh.
                   Khong dung Employee.department cua manager: moi manager deu nam o
                   "Management - EC" (nhom nop bao cao), khong phai phong that.
  * Con lai      : chi chinh minh.
Moi loc (phong, khoang ngay) deu bi kep vao pham vi nay o server - trang khong tu quyet.
"""
import datetime

import frappe
from frappe import _

from ecentric_workspace.platform.ai import usage_report as report
from ecentric_workspace.platform.ai.usage import DOCTYPE

ALL_ROLES = ("System Manager", "EC CEO", "EC AI Usage Viewer")
MAX_DAYS = 366
ROW_FIELDS = ["user", "department", "purpose", "model", "ok", "latency_ms", "total_tokens",
              "credits", "cost_source", "images", "creation"]
FORMFILL_LOG = "EC AI Formfill Log"


def scope_for(user):
    roles = set(frappe.get_roles(user))
    if roles & set(ALL_ROLES):
        return {"kind": "all", "departments": []}
    try:
        depts = frappe.get_all("Department", filters={"manager_email": user, "disabled": 0},
                               pluck="name")
    except Exception:
        depts = []
    if depts:
        return {"kind": "dept", "departments": sorted(depts)}
    return {"kind": "self", "departments": []}


def _people(scope, user, department):
    filters = {"status": "Active", "user_id": ["is", "set"]}
    if scope["kind"] == "self":
        filters["user_id"] = user
    elif scope["kind"] == "dept":
        filters["department"] = ["in", [department] if department else scope["departments"]]
    elif department:
        filters["department"] = department
    rows = frappe.get_all("Employee", filters=filters,
                          fields=["user_id", "employee_name", "department"])
    out = {r.user_id: {"name": r.employee_name, "department": r.department} for r in rows}
    if scope["kind"] in ("self", "dept") and user not in out and not department:
        out[user] = {"name": frappe.db.get_value("User", user, "full_name") or user,
                     "department": ""}
    return out


def _dates(from_date, to_date, days):
    today = datetime.date.fromisoformat(frappe.utils.nowdate())
    try:
        end = datetime.date.fromisoformat(str(to_date)[:10]) if to_date else today
        start = (datetime.date.fromisoformat(str(from_date)[:10]) if from_date
                 else end - datetime.timedelta(days=max(1, int(days or 30)) - 1))
    except ValueError:
        frappe.throw(_("Ngày không hợp lệ."))
    if start > end:
        start, end = end, start
    if (end - start).days >= MAX_DAYS:
        start = end - datetime.timedelta(days=MAX_DAYS - 1)
    return start, end


def _rows(scope, people, department, start, end):
    filters = [["creation", ">=", "%s 00:00:00" % start], ["creation", "<=", "%s 23:59:59" % end]]
    if scope["kind"] != "all" or department:
        if not people:
            return []
        filters.append(["user", "in", list(people)])
    return frappe.get_all(DOCTYPE, filters=filters, fields=ROW_FIELDS, limit_page_length=0,
                          order_by="creation asc")


def _formfill(scope, people, department, start, end):
    try:
        filters = [["creation", ">=", "%s 00:00:00" % start],
                   ["creation", "<=", "%s 23:59:59" % end]]
        if scope["kind"] != "all" or department:
            filters.append(["request_user", "in", list(people) or [""]])
        logs = frappe.get_all(FORMFILL_LOG, filters=filters,
                              fields=["outcome", "business_doc", "approval_code"],
                              limit_page_length=0)
        from ecentric_workspace.approval_center.shared.registry import get_definition
        by_code, statuses = {}, {}
        for l in logs:
            if l.business_doc:
                by_code.setdefault(l.approval_code, []).append(l.business_doc)
        for code, names in by_code.items():
            dt = get_definition(code).business_doctype
            for r in frappe.get_all(dt, filters={"name": ["in", names]},
                                    fields=["name", "approval_status"]):
                statuses[r.name] = r.approval_status
        return report.funnel([dict(l) for l in logs], statuses)
    except Exception:
        frappe.log_error(title="ai_usage formfill funnel")
        return None


@frappe.whitelist(methods=["GET"])
def summary(from_date=None, to_date=None, days=30, department=None):
    user = frappe.session.user
    if not user or user == "Guest":
        raise frappe.PermissionError
    scope = scope_for(user)
    department = (department or "").strip() or None
    if department and scope["kind"] == "self":
        department = None
    if department and scope["kind"] == "dept" and department not in scope["departments"]:
        raise frappe.PermissionError
    start, end = _dates(from_date, to_date, days)
    people = _people(scope, user, department)
    data = report.aggregate(_rows(scope, people, department, start, end), people, start, end)
    data.update({
        "scope": scope, "department": department or "",
        "period": {"from": str(start), "to": str(end)},
        "formfill": _formfill(scope, people, department, start, end),
        "departments": (scope["departments"] if scope["kind"] == "dept" else
                        sorted({p["department"] for p in _people(scope, user, None).values()
                                if p["department"]}) if scope["kind"] == "all" else []),
        "usd_per_credit": report.USD_PER_CREDIT,
    })
    return data

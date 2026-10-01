# Copyright (c) 2026, eCentric and contributors
"""Them 2 cot "NV chot cong" / "Lead chot cong" vao bao cao HRMS Monthly Attendance Sheet.

01/10/2026 - CnB xem bang cong muon thay luon ai da chot. Hoan chon them cot vao bao cao
goc thay vi bao cao rieng. KHONG sua HRMS: lop Report cua site (override_doctype_class)
goi `execute` cua HRMS y nguyen roi moi gan them hai cot (xem report_override.py).

Phan nay THUAN (khong import frappe) de test bang python tran. FAIL-SAFE o ben goi:
loi o day thi tra lai ket qua goc cua HRMS, bang cong khong bao gio vo vi hai cot nay.
"""
import datetime as _dt

REPORT_NAME = "Monthly Attendance Sheet"
COL_MEMBER = "ec_nv_chot_cong"
COL_LEAD = "ec_lead_chot_cong"

ST_OPEN = "Open"
ST_MEMBER = "Member Closed"
ST_CLOSED = "Closed"
MODE_SELF = "Tu chot"
MODE_LEAD = "Leader chot thay"
MODE_HR = "HR chot thay"


def _dt_of(v):
    if not v:
        return None
    if isinstance(v, _dt.datetime):
        return v
    try:
        return _dt.datetime.fromisoformat(str(v)[:19])
    except ValueError:
        return None


def _hm(v):
    d = _dt_of(v)
    return d.strftime("%d/%m %H:%M") if d else ""


def _late(at, due):
    a, b = _dt_of(at), _dt_of(due)
    return bool(a and b and a > b)


def period_from_filters(filters):
    """'YYYY-MM' cua ky dang xem, hoac None neu khong xac dinh duoc MOT thang."""
    f = filters or {}
    if (f.get("filter_based_on") or "Month") == "Month":
        try:
            y, m = int(f.get("year")), int(f.get("month"))
        except (TypeError, ValueError):
            return None
        return "%04d-%02d" % (y, m) if 1 <= m <= 12 else None
    s, e = str(f.get("start_date") or "")[:7], str(f.get("end_date") or "")[:7]
    return s if s and s == e else None


def member_text(row):
    """Cot NV: nhan vien tu chot luc nao / ai chot thay / chua chot."""
    if not row:
        return ""
    if row.get("status") == ST_OPEN:
        return "Chưa chốt"
    mode = row.get("close_mode") or MODE_SELF
    if mode == MODE_LEAD:
        return "Leader chốt thay"
    if mode == MODE_HR:
        return "CnB/HR chốt thay"
    t = "Đã chốt " + _hm(row.get("member_closed_at"))
    return t + (" (trễ)" if _late(row.get("member_closed_at"), row.get("member_deadline")) else "")


def lead_text(row):
    """Cot Lead: leader (hoac CnB/HR voi nguoi khong co quan ly) da chot ca team chua."""
    if not row:
        return ""
    if row.get("status") != ST_CLOSED:
        return "Chưa chốt" if row.get("lead_user") else "Chưa chốt (CnB/HR)"
    who = "Đã chốt " if row.get("lead_user") else "CnB/HR đã chốt "
    t = who + _hm(row.get("team_closed_at"))
    return t + (" (trễ)" if _late(row.get("team_closed_at"), row.get("lead_deadline")) else "")


def add_columns(result, rows_by_employee):
    """result = tuple/list HRMS tra ve (columns, data, ...). Tra ve list moi, khong sua tai cho.
    `rows_by_employee`: {employee: dict dong EC Timesheet Close}."""
    if not result:
        return result
    res = list(result)
    columns, data = list(res[0] or []), res[1] or []
    if not columns or COL_MEMBER in [c.get("fieldname") if isinstance(c, dict) else None for c in columns]:
        return result
    names = [c.get("fieldname") if isinstance(c, dict) else None for c in columns]
    at = names.index("employee_name") + 1 if "employee_name" in names else len(columns)
    columns[at:at] = [
        {"label": "NV chốt công", "fieldname": COL_MEMBER, "fieldtype": "Data", "width": 150},
        {"label": "Lead chốt công", "fieldname": COL_LEAD, "fieldtype": "Data", "width": 150},
    ]
    for d in data:
        if isinstance(d, dict) and d.get("employee"):
            r = rows_by_employee.get(d["employee"])
            d[COL_MEMBER] = member_text(r)
            d[COL_LEAD] = lead_text(r)
    res[0] = columns
    return res

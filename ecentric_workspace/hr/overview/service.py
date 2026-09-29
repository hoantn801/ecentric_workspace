# Copyright (c) 2026, eCentric and contributors
"""Dung du lieu cho the Nhan su (Bang dieu khien / Danh sach / So do phong ban).

THUAN PYTHON - khong import frappe: nhan list dict tu repository + tap permlevel nguoi xem
+ ngay hom nay, tra ve dict da san sang de ve. Test chay khong can bench.

KHONG CO SO LUONG o bat ky dau. Truong ca nhan (L1) chi duoc dung de KIEM co/khong khi
nguoi xem co L1; nguoi khong co L1 thi khong kiem, de khong lo ca viec 'co hay khong co'."""
import datetime

from ecentric_workspace.hr.overview import constants as C
from ecentric_workspace.hr.overview.org_builder import build_org, dept_label

TRIAL_TYPES = ("Probation", "Intern")


def _d(v):
    if not v:
        return None
    if isinstance(v, datetime.date):
        return v if not isinstance(v, datetime.datetime) else v.date()
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def vn_date(v):
    d = _d(v)
    return d.strftime("%d/%m/%Y") if d else ""




def latest_contracts(rows):
    """parent -> hop dong co tu_ngay moi nhat."""
    out = {}
    for r in rows:
        cur = out.get(r["parent"])
        if cur is None or (_d(r.get("tu_ngay")) or datetime.date.min) > (_d(cur.get("tu_ngay")) or datetime.date.min):
            out[r["parent"]] = r
    return out


def missing_labels(emp, levels):
    out = []
    for field, label, level in C.REQUIRED_CHECKS:
        if level not in levels:
            continue
        if field not in emp:
            continue          # khong doc duoc truong nay (permlevel / mask) -> khong kiem
        if field == "reports_to" and emp.get("grade") in C.NO_MANAGER_GRADES:
            continue
        if not emp.get(field):
            out.append(label)
    return out


class BuildHrOverviewService:
    def execute(self, emps, contract_rows, depts, memberships, levels, today):
        today = _d(today)
        levels = set(levels or [0])
        latest = latest_contracts(contract_rows) if 2 in levels else {}
        by_name = {e["name"]: e for e in emps}
        by_user = {e.get("user_id"): e for e in emps if e.get("user_id")}
        rows = [self._row(e, latest.get(e["name"]), by_name, levels, today) for e in emps]
        return {
            "stats": self._stats(rows, emps),
            "todo": self._todo(rows),
            "by_dept": self._by_dept(rows),
            "directory": rows,
            "org": build_org(rows, depts, by_user, memberships, by_name),
            "has_contracts": 2 in levels,
            "checks_personal": 1 in levels,
        }

    def _row(self, e, con, by_name, levels, today):
        end = _d(con.get("den_ngay")) if con else None
        no_term = bool(con and con.get("khong_thoi_han"))
        days = (end - today).days if (end and today and not no_term) else None
        mgr = by_name.get(e.get("reports_to")) or {}
        return {
            "name": e["name"], "employee_name": e.get("employee_name") or e["name"],
            "employee_number": e.get("employee_number") or "",
            "department": e.get("department") or "", "dept": dept_label(e.get("department")),
            "sub": e.get("ec_sub_department") or "", "designation": e.get("designation") or "",
            "grade": e.get("grade") or "", "employment_type": e.get("employment_type") or "",
            "manager": mgr.get("employee_name") or "", "user_id": e.get("user_id") or "",
            "date_of_joining": str(e.get("date_of_joining") or "")[:10],
            "contract_type": (con or {}).get("loai_hop_dong") or "",
            "contract_end": str(end) if end else "", "no_term": no_term,
            "contract_warn": days is not None and 0 <= days <= C.CONTRACT_WARN_DAYS,
            "probation_warn": bool(con and con.get("loai_hop_dong") == C.PROBATION
                                   and days is not None and 0 <= days <= C.PROBATION_WARN_DAYS),
            "days_left": days,
            "missing": missing_labels(e, levels),
            "trial": (e.get("employment_type") or "") in TRIAL_TYPES,
        }

    def _stats(self, rows, emps):
        types = {}
        for e in emps:
            t = e.get("employment_type") or "Khác"
            types[t] = types.get(t, 0) + 1
        return {
            "active": len(rows), "by_type": types,
            "contract_warn": sum(1 for r in rows if r["contract_warn"] and not r["probation_warn"]),
            "probation_warn": sum(1 for r in rows if r["probation_warn"]),
            "missing": sum(1 for r in rows if r["missing"]),
        }

    def _todo(self, rows):
        items = []
        for r in rows:
            if r["probation_warn"]:
                items.append({"kind": "probation", "row": r["name"], "days": r["days_left"],
                              "text": "Kết thúc thử việc " + vn_date(r["contract_end"])})
            elif r["contract_warn"]:
                items.append({"kind": "contract", "row": r["name"], "days": r["days_left"],
                              "text": (r["contract_type"] or "Hợp đồng") + " hết hạn " + vn_date(r["contract_end"])})
            if r["missing"]:
                items.append({"kind": "missing", "row": r["name"], "days": 999,
                              "text": "Thiếu: " + ", ".join(r["missing"])})
        items.sort(key=lambda i: (i["days"], i["kind"]))
        return items

    def _by_dept(self, rows):
        agg = {}
        for r in rows:
            a = agg.setdefault(r["department"], {"department": r["department"], "label": r["dept"],
                                                 "official": 0, "trial": 0})
            a["trial" if r["trial"] else "official"] += 1
        out = sorted(agg.values(), key=lambda a: -(a["official"] + a["trial"]))
        for a in out:
            a["total"] = a["official"] + a["trial"]
        return out

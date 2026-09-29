# Copyright (c) 2026, eCentric and contributors
"""Tab So do phong ban: moi phong mot the (truong phong, so nguoi, sub, co canh bao).
Thuan Python. Truong phong = manager_email cua Department, nhung chi tinh la 'co truong
phong' khi grade la Truong phong / BOD (Service hien de trong - manager_email la nhan vien
chi de giu luong duyet)."""
from ecentric_workspace.hr.overview import constants as C


def dept_label(name):
    name = name or ""
    return name[:-len(C.DEPT_SUFFIX)] if name.endswith(C.DEPT_SUFFIX) else name


def build_org(rows, depts, by_user, memberships, by_name):
    manages = {}
    for m in memberships or []:
        e = by_name.get(m["parent"])
        if e and e.get("department") == C.MANAGEMENT_DEPT:
            manages.setdefault(m["department"], []).append(e.get("employee_name") or e["name"])
    out = []
    for d in depts:
        members = [r for r in rows if r["department"] == d["name"]]
        if not members:
            continue
        head = by_user.get(d.get("manager_email")) or {}
        subs = {}
        for r in members:
            key = r["sub"] or ""
            subs[key] = subs.get(key, 0) + 1
        out.append({
            "department": d["name"], "label": dept_label(d["name"]), "total": len(members),
            "head": head.get("employee_name") or "",
            "head_ok": (head.get("grade") in C.HEAD_GRADES) or d["name"] == C.MANAGEMENT_DEPT,
            "managed_by": manages.get(d["name"], []),
            "is_management": d["name"] == C.MANAGEMENT_DEPT,
            "subs": [{"name": k, "count": v} for k, v in
                     sorted(subs.items(), key=lambda kv: (kv[0] == "", -kv[1]))],
            "flags": {"contract": sum(1 for r in members if r["contract_warn"] and not r["probation_warn"]),
                      "probation": sum(1 for r in members if r["probation_warn"]),
                      "missing": sum(1 for r in members if r["missing"])},
        })
    out.sort(key=lambda o: (o["is_management"], -o["total"]))
    return out

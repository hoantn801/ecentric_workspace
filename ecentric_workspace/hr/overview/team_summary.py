# Copyright (c) 2026, eCentric and contributors
"""Hai tab tong hop cho CnB tren /tong-quan#nhan-su - Hoan 01/10/2026.

  * SLA: % dung han cua tung nguoi trong ky, gop theo phong ban. Cung mot cong thuc
    voi trang /sla: goi lai sla.domain.scoring.aggregate, KHONG tinh lai o day - hai
    con so cho cung mot nguoi tren hai trang ma lech nhau thi khong ai tin trang nao.
  * Phan bo cong viec (brand weight): ai da chot / dang cho ai duyet / bi tra lai /
    chua nop, va ty trong chung (quy ra so nguoi, FTE) cua cong ty / tung phong tinh tu
    cac phieu DA CHOT.

Thuan Python, khong import frappe: team_summary_repo doc DB roi dua vao day.
Khong co truong luong nao.
"""
from ecentric_workspace.approval_center.features.brand_weight.domain.status import status_of
from ecentric_workspace.sla.constants import ALL_GROUPS, GROUP_LABEL, GROUP_MIN_SAMPLE, GROUP_SORT
from ecentric_workspace.sla.domain import scoring

NO_DEPT_LABEL = "Chưa gán phòng"
#: Cung nguong voi /sla va the %SLA o trang chu (90 / 70).
RATE_GOOD = 90
RATE_WARN = 70
#: Phieu Rut / Tu choi khong con song - giong brand_weight_repository.find_doc.
CLOSED = ("Rejected", "Cancelled")
PENDING = ("wait_lead", "wait_head")


def _rate(ontime, scored):
    return round(ontime * 100.0 / scored, 1) if scored else None


def band(rate):
    if rate is None:
        return "none"
    if rate >= RATE_GOOD:
        return "good"
    if rate >= RATE_WARN:
        return "warn"
    return "bad"


def _dept_label(depts, key):
    return ((depts.get(key) or {}).get("label")) or key or NO_DEPT_LABEL


def _sort_by_rate(items):
    # Can chu y truoc: ti le thap len dau, "chua co dau viec" xuong cuoi.
    return sorted(items, key=lambda x: (x["rate"] is None, x["rate"] if x["rate"] is not None else 0,
                                        x.get("name") or x.get("label") or ""))


# ---------------------------------------------------------------- SLA
def build_sla(rows, people, depts, period, now):
    """rows   : dong EC SLA Obligation cua ky (da bo Cancelled)
                {owner_user, department, group_key, counts_toward_sla, status, due_at, paused_seconds}
    people : {user: {"name", "department", "active"}} - nhan vien dang lam + chu cua cac dong
    depts  : {department: {"label", "manager"}}
    """
    by_user, dept_of = {}, {}
    for r in rows:
        u = r.get("owner_user")
        if not u:
            continue
        by_user.setdefault(u, []).append(r)
        if r.get("department"):
            # Phong DA CHUP tren nghia vu (giong /sla): nguoi chuyen phong giua thang
            # van tinh vao phong ma dau viec phat sinh.
            dept_of[u] = r["department"]
    users = set(by_user) | {u for u, p in people.items() if p.get("active")}

    groups_meta = [{"key": g, "label": GROUP_LABEL.get(g, g), "counts": bool(scoring.counts_in_period(g, period))}
                   for g in sorted(ALL_GROUPS, key=lambda k: GROUP_SORT.get(k, 999))]
    tot = {"ontime": 0, "scored": 0}
    gtot = {g["key"]: {"ontime": 0, "scored": 0} for g in groups_meta}
    grouped = {}
    for u in users:
        p = people.get(u) or {}
        agg = scoring.aggregate(by_user.get(u, []), now=now, min_sample_by_group=GROUP_MIN_SAMPLE)
        ov = agg["overall"]
        gs = {}
        for g, b in agg["groups"].items():
            if g in gtot:
                gtot[g]["ontime"] += b["ontime"]
                gtot[g]["scored"] += b["scored"]
            if b["scored"] or b["open"]:
                gs[g] = {"rate": b["rate"], "scored": b["scored"], "ontime": b["ontime"],
                         "late": b["late"], "missed": b["missed"], "open": b["open"]}
        tot["ontime"] += ov["ontime"]
        tot["scored"] += ov["scored"]
        dept = dept_of.get(u) or p.get("department") or ""
        grouped.setdefault(dept, []).append({
            "user": u, "name": p.get("name") or u.split("@")[0], "left": not p.get("active"),
            "rate": ov["rate"], "band": band(ov["rate"]), "scored": ov["scored"], "ontime": ov["ontime"],
            "late": ov["late"], "missed": ov["missed"], "open": ov["open"], "groups": gs,
        })

    out = []
    for key, ms in grouped.items():
        ontime = sum(m["ontime"] for m in ms)
        scored = sum(m["scored"] for m in ms)
        rate = _rate(ontime, scored)
        out.append({
            "department": key, "label": _dept_label(depts, key), "manager": (depts.get(key) or {}).get("manager"),
            "rate": rate, "band": band(rate), "scored": scored, "ontime": ontime,
            "people": len(ms), "bad": sum(1 for m in ms if m["band"] == "bad"),
            "warn": sum(1 for m in ms if m["band"] == "warn"),
            "members": _sort_by_rate(ms),
        })
    members = [m for d in out for m in d["members"]]
    rate = _rate(tot["ontime"], tot["scored"])
    return {
        "period": period,
        "groups": [dict(g, rate=_rate(gtot[g["key"]]["ontime"], gtot[g["key"]]["scored"]),
                        scored=gtot[g["key"]]["scored"]) for g in groups_meta],
        "stats": {"rate": rate, "band": band(rate), "scored": tot["scored"], "people": len(members),
                  "good": sum(1 for m in members if m["band"] == "good"),
                  "warn": sum(1 for m in members if m["band"] == "warn"),
                  "bad": sum(1 for m in members if m["band"] == "bad"),
                  "none": sum(1 for m in members if m["band"] == "none")},
        "departments": _sort_by_rate(out),
    }


# ---------------------------------------------------------------- Brand weight
def live_docs(docs):
    """{employee: doc} - phieu con song moi nhat cua tung nguoi trong ky."""
    out = {}
    for d in sorted(docs, key=lambda x: str(x.get("creation") or ""), reverse=True):
        emp = d.get("employee")
        if not emp or emp in out:
            continue
        if d.get("approval_status") in CLOSED:
            continue
        out[emp] = d
    return out


def _mix(weight_maps, labels):
    fte = {}
    for w in weight_maps:
        for b, v in (w or {}).items():
            fte[b] = fte.get(b, 0.0) + float(v or 0) / 100.0
    total = sum(fte.values())
    rows = [{"id": b, "label": labels.get(b) or b, "fte": round(v, 2),
             "share": round(v * 100.0 / total, 1) if total else 0.0} for b, v in fte.items() if v]
    return sorted(rows, key=lambda r: (-r["fte"], r["label"].lower()))


def build_brand(expected, docs, details, waiting_on, labels, depts, period):
    """expected  : [{employee, name, department}] - nhan vien dang lam, co tai khoan (phai nop)
    docs      : [{name, employee, employee_name, department, creation, approval_request,
                  approval_status, current_level}] - moi phieu cua ky
    details   : {doc name: {brand: weight}}
    waiting_on: {approval_request: [ten nguoi dang phai duyet]}
    labels    : {brand id: ten hien thi}
    """
    live = live_docs(docs)
    people = {e["employee"]: dict(e) for e in expected}
    for emp, d in live.items():
        # Phieu cua nguoi da nghi / doi tai khoan van phai hien: so cua ho da vao PnL.
        people.setdefault(emp, {"employee": emp, "name": d.get("employee_name") or emp,
                                "department": d.get("department") or ""})
    grouped = {}
    for emp, p in people.items():
        d = live.get(emp)
        st = status_of({"approval_status": d.get("approval_status"), "current_level": d.get("current_level")}) if d else "none"
        grouped.setdefault(p.get("department") or "", []).append({
            "employee": emp, "name": p.get("name") or emp, "status": st, "doc": d and d.get("name"),
            "weights": dict(details.get(d["name"], {})) if d else {},
            "waiting_on": waiting_on.get(d.get("approval_request"), []) if d and st in PENDING else [],
        })

    order = {"none": 0, "returned": 1, "draft": 2, "wait_lead": 3, "wait_head": 4, "final": 5}

    def counts(ms):
        c = {k: 0 for k in order}
        for m in ms:
            c[m["status"]] = c.get(m["status"], 0) + 1
        return c

    out = []
    for key, ms in grouped.items():
        c = counts(ms)
        out.append({
            "department": key, "label": _dept_label(depts, key), "manager": (depts.get(key) or {}).get("manager"),
            "total": len(ms), "final": c["final"], "pending": c["wait_lead"] + c["wait_head"],
            "returned": c["returned"], "none": c["none"] + c["draft"],
            "state": "done" if c["final"] == len(ms) else ("none" if c["none"] + c["draft"] == len(ms) else "partial"),
            "mix": _mix([m["weights"] for m in ms if m["status"] == "final"], labels),
            "members": sorted(ms, key=lambda m: (order.get(m["status"], 9), m["name"] or "")),
        })
    out.sort(key=lambda x: ({"none": 0, "partial": 1, "done": 2}[x["state"]], x["label"]))
    allm = [m for d in out for m in d["members"]]
    c = counts(allm)
    used = sorted({b for m in allm for b in m["weights"]}, key=lambda b: (labels.get(b) or b).lower())
    return {
        "period": period,
        "stats": {"total": len(allm), "final": c["final"], "wait_lead": c["wait_lead"],
                  "wait_head": c["wait_head"], "returned": c["returned"], "none": c["none"] + c["draft"]},
        "mix": _mix([m["weights"] for m in allm if m["status"] == "final"], labels),
        "brands": [{"id": b, "label": labels.get(b) or b} for b in used],
        "departments": out,
    }


# ---------------------------------------------------------------- Xuat Excel
BW_STATUS_LABEL = {"final": "Đã chốt", "wait_lead": "Chờ lead", "wait_head": "Chờ trưởng phòng",
                   "returned": "Bị trả lại", "draft": "Chưa nộp", "none": "Chưa nộp"}


def _month(period):
    return "%d-%s" % (int(period[5:7]), period[:4])


def sla_sheets(d):
    """-> (ten tep, [(ten sheet, [hang])]). Hang dau la tieu de. % de dang so (92.5 = 92,5%)."""
    groups = d["groups"]
    people = [["Phòng", "Nhân viên", "Email", "% SLA", "Đúng hạn", "Đã chấm", "Trễ", "Bỏ lỡ", "Đang mở", "Đã nghỉ"]
              + ["%% %s" % g["label"] for g in groups]]
    for dep in sorted(d["departments"], key=lambda x: x["label"]):
        # Tep Excel de tra cuu: xep theo phong roi theo ten (tren man hinh thi can chu y len dau).
        for m in sorted(dep["members"], key=lambda x: x["name"] or ""):
            people.append([dep["label"], m["name"], m["user"], m["rate"], m["ontime"], m["scored"], m["late"],
                           m["missed"], m["open"], "x" if m["left"] else ""]
                          + [(m["groups"].get(g["key"]) or {}).get("rate") for g in groups])
    depts = [["Phòng", "Trưởng phòng", "Số người", "% SLA", "Đúng hạn", "Đã chấm", "Dưới 70%", "70 – 90%"]]
    for dep in d["departments"]:
        depts.append([dep["label"], dep["manager"] or "", dep["people"], dep["rate"], dep["ontime"], dep["scored"],
                      dep["bad"], dep["warn"]])
    st = d["stats"]
    depts.append(["Toàn công ty", "", st["people"], st["rate"], "", st["scored"], st["bad"], st["warn"]])
    grp = [["Nhóm việc", "Tính vào % SLA", "% đúng hạn", "Đã chấm"]]
    for g in groups:
        grp.append([g["label"], "Có" if g["counts"] else "Không (ngoài %SLA kỳ này)", g["rate"], g["scored"]])
    return ("SLA_thang_%s.xlsx" % _month(d["period"]),
            [("Theo người", people), ("Theo phòng", depts), ("Theo nhóm việc", grp)])


def brand_sheets(d):
    brands = d["brands"]
    people = [["Phòng", "Nhân viên", "Mã NV", "Trạng thái", "Đang chờ"] + ["%s (%%)" % b["label"] for b in brands]
              + ["Tổng (%)"]]
    for dep in sorted(d["departments"], key=lambda x: x["label"]):
        # Tep Excel de tra cuu: xep theo phong roi theo ten (tren man hinh thi can chu y len dau).
        for m in sorted(dep["members"], key=lambda x: x["name"] or ""):
            w = m["weights"]
            people.append([dep["label"], m["name"], m["employee"], BW_STATUS_LABEL.get(m["status"], m["status"]),
                           ", ".join(m["waiting_on"])] + [w.get(b["id"]) for b in brands]
                          + [round(sum(w.values()), 2) if w else None])
    mix = [["Brand", "Số người (FTE)", "Tỷ trọng (%)"]] + [[b["label"], b["fte"], b["share"]] for b in d["mix"]]
    mix.append(["Tổng (phiếu đã chốt)", round(sum(b["fte"] for b in d["mix"]), 2), 100 if d["mix"] else None])
    depts = [["Phòng", "Trưởng phòng", "Phải nộp", "Đã chốt", "Chờ duyệt", "Bị trả lại", "Chưa nộp"]
             + ["%s (FTE)" % b["label"] for b in brands]]
    for dep in d["departments"]:
        fte = {b["id"]: b["fte"] for b in dep["mix"]}
        depts.append([dep["label"], dep["manager"] or "", dep["total"], dep["final"], dep["pending"],
                      dep["returned"], dep["none"]] + [fte.get(b["id"]) for b in brands])
    return ("Phan_bo_cong_viec_thang_%s.xlsx" % _month(d["period"]),
            [("Theo người", people), ("Tỷ trọng công ty", mix), ("Theo phòng", depts)])

# Copyright (c) 2026, eCentric and contributors
"""Doi phieu tra loi thanh bang chu (xuat Excel). Thuan - khong cham frappe.

Moi cau hoi mot cot; luoi thi moi HANG cua luoi mot cot ("Câu - hàng"). Gia tri ghi bang
NHAN nguoi doc hieu duoc (ten lua chon), khong phai id noi bo."""
from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.domain import schema


def _labels(items):
    return {o["id"]: o["label"] for o in items or []}


def cell(q, v):
    if v in (None, "", [], {}):
        return ""
    t = q["type"]
    if t in C.CHOICE_TYPES:
        lb = _labels(q.get("options"))
        parts = [lb.get(x, x) for x in (v.get("sel") or [])]
        if v.get("other"):
            parts.append("Khác: %s" % v["other"])
        return "; ".join(parts)
    if t == C.Q_RANKING:
        lb = _labels(q.get("options"))
        return "; ".join("%d. %s" % (i, lb.get(x, x)) for i, x in enumerate(v, 1))
    if t == C.Q_FILE:
        return "; ".join(f.get("name") or f.get("url") for f in v)
    return v if isinstance(v, (int, float)) else str(v)


def header(form, anonymous, quiz):
    cols = ["Thời gian nộp"] + ([] if anonymous else ["Người trả lời", "Email"])
    if quiz:
        cols.append("Điểm")
    for n, q in enumerate(schema.questions(form), 1):
        title = "%d. %s" % (n, q.get("title") or "")
        if q["type"] in C.GRID_TYPES:
            cols.extend("%s - %s" % (title, r["label"]) for r in q.get("rows") or [])
        else:
            cols.append(title)
    return cols


def table(form, rows, names, anonymous, quiz):
    out = [header(form, anonymous, quiz)]
    qs = schema.questions(form)
    for r in rows:
        a = r.get("answers") or {}
        line = [str(r.get("submitted_at") or "")[:19]]
        if not anonymous:
            line += [names.get(r.get("respondent"), r.get("respondent") or ""), r.get("respondent") or ""]
        if quiz:
            line.append("%s/%s" % (_n(r.get("score")), _n(r.get("max_score"))))
        for q in qs:
            v = a.get(q["id"])
            if q["type"] in C.GRID_TYPES:
                cl = _labels(q.get("cols"))
                for row in q.get("rows") or []:
                    x = (v or {}).get(row["id"]) if isinstance(v, dict) else None
                    if isinstance(x, list):
                        line.append("; ".join(cl.get(c, c) for c in x))
                    else:
                        line.append(cl.get(x, x or ""))
            else:
                line.append(cell(q, v))
        out.append(line)
    return out


def _n(v):
    if v is None:
        return 0
    return int(v) if float(v) == int(v) else v

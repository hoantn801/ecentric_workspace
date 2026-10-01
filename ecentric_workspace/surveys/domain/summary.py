# Copyright (c) 2026, eCentric and contributors
"""Tong hop ket qua theo tung cau hoi (tab "Kết quả" cua trinh soan + tom tat cho nguoi
tra loi neu nguoi tao bat). Thuan: nhan form + danh sach answers dict."""
from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.domain import schema


def _choice(q, rows):
    counts = {o["id"]: 0 for o in q.get("options") or []}
    other, others, n = 0, [], 0
    for a in rows:
        v = a.get(q["id"])
        if not isinstance(v, dict):
            continue
        n += 1
        for s in v.get("sel") or []:
            if s in counts:
                counts[s] += 1
        if v.get("other"):
            other += 1
            if len(others) < C.TEXT_SAMPLES:
                others.append(v["other"])
    return {"answered": n, "counts": counts, "other": other, "other_samples": others}


def _numbers(q, rows, lo, hi):
    dist = {str(k): 0 for k in range(lo, hi + 1)}
    vals = []
    for a in rows:
        v = a.get(q["id"])
        if isinstance(v, int) and lo <= v <= hi:
            dist[str(v)] += 1
            vals.append(v)
    avg = round(float(sum(vals)) / len(vals), 2) if vals else None
    out = {"answered": len(vals), "distribution": dist, "average": avg}
    if q["type"] == C.Q_SCALE and lo == 0 and hi == 10 and vals:
        # Thang 0-10 = NPS: % de cu (9-10) tru % che (0-6).
        pro = sum(1 for x in vals if x >= 9)
        det = sum(1 for x in vals if x <= 6)
        out["nps"] = round(100.0 * (pro - det) / len(vals))
    return out


def _grid(q, rows):
    cols = [c["id"] for c in q.get("cols") or []]
    table = {r["id"]: {c: 0 for c in cols} for r in q.get("rows") or []}
    n = 0
    for a in rows:
        v = a.get(q["id"])
        if not isinstance(v, dict):
            continue
        n += 1
        for r, picked in v.items():
            if r not in table:
                continue
            for c in (picked if isinstance(picked, list) else [picked]):
                if c in table[r]:
                    table[r][c] += 1
    return {"answered": n, "table": table}


def _ranking(q, rows):
    ids = [o["id"] for o in q.get("options") or []]
    sums, n = {i: 0 for i in ids}, 0
    for a in rows:
        v = a.get(q["id"])
        if not isinstance(v, list) or sorted(v) != sorted(ids):
            continue
        n += 1
        for pos, i in enumerate(v, 1):
            sums[i] += pos
    avg = {i: (round(float(sums[i]) / n, 2) if n else None) for i in ids}
    return {"answered": n, "average_rank": avg}


def _texts(q, rows):
    vals = [a.get(q["id"]) for a in rows if a.get(q["id"]) not in (None, "", [])]
    return {"answered": len(vals), "samples": vals[:C.TEXT_SAMPLES]}


def summarize(form, answer_rows):
    """answer_rows: [answers dict] moi nhat truoc. Tra {"total", "questions": {qid: {...}}}."""
    out = {}
    for q in schema.questions(form):
        t = q["type"]
        if t in C.CHOICE_TYPES:
            out[q["id"]] = _choice(q, answer_rows)
        elif t == C.Q_SCALE:
            out[q["id"]] = _numbers(q, answer_rows, q.get("scale_min", 1), q.get("scale_max", 5))
        elif t == C.Q_RATING:
            out[q["id"]] = _numbers(q, answer_rows, 1, q.get("rating_max", 5))
        elif t in C.GRID_TYPES:
            out[q["id"]] = _grid(q, answer_rows)
        elif t == C.Q_RANKING:
            out[q["id"]] = _ranking(q, answer_rows)
        else:
            out[q["id"]] = _texts(q, answer_rows)
    return {"total": len(answer_rows), "questions": out}


def public_summary(form, answer_rows):
    """Ban tom tat cho NGUOI TRA LOI (khi nguoi tao bat): chi so dem / trung binh, KHONG kem
    cau tra loi chu tu do va tep (co the lo danh tinh hoac noi dung rieng)."""
    full = summarize(form, answer_rows)
    for q in schema.questions(form):
        s = full["questions"].get(q["id"]) or {}
        s.pop("samples", None)
        s.pop("other_samples", None)
    return full

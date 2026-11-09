# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu dot 3 - quy tac THUAN cho viec sua + duyet quy tac thoi han (khong cham DB,
khong import frappe). Dung chung voi domain.rules_view (dang {days{key}, mult{muc}}).

  * normalize_input: du lieu team Data nhap (so ngay theo loai, he so theo muc) -> gia tri sach,
    hoac D.Invalid kem loi tieng Viet. Thieu khoa nao -> giu gia tri dang ap dung.
  * diff: [{key, label, kind (days|mult), old, new}] giua hai bo - dung cho cot "Đề xuất mới",
    lich su phien ban (cu -> moi) va noi dung thong bao.
  * to_doc / from_doc: dang ban ghi EC Data SLA Rule Set (items + mult_*).
"""
import math
import re

from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import domain as D

_INT_RE = re.compile(r"^\s*-?\d+\s*$")
_NUM_RE = re.compile(r"^\s*-?\d+([.,]\d+)?\s*$")


def rule_keys():
    return [r[0] for r in C.RULE_DEFAULTS]


def fmt_mult(v):
    """0.5 -> "0,5"; 1.0 -> "1" (cach viet tren trang - dau phay thap phan)."""
    return ("%g" % float(v)).replace(".", ",")


def _int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v == math.floor(v) else None
    s = str(v if v is not None else "")
    return int(s) if _INT_RE.match(s) else None


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v if v is not None else "")
    return float(s.replace(",", ".")) if _NUM_RE.match(s) else None


def normalize_input(data, active):
    """data = {days: {rule_key: n}, mult: {muc: x}, reason}; active = rules_view hien hanh.
    -> {days, mult, reason}. Nem D.Invalid (moi loi mot dong)."""
    data = data or {}
    labels = active["labels"]
    errs = []
    days_in = data.get("days") or {}
    mult_in = data.get("mult") or {}
    if not isinstance(days_in, dict) or not isinstance(mult_in, dict):
        raise D.Invalid(["Dữ liệu quy tắc không hợp lệ."])
    unknown = [k for k in days_in if k not in labels] + [k for k in mult_in if k not in C.PRIORITIES]
    if unknown:
        errs.append("Không có mục quy tắc: {0}.".format(", ".join(sorted(str(k) for k in unknown))))
    days = {}
    for key in rule_keys():
        if key not in days_in or days_in.get(key) in (None, ""):
            days[key] = int(active["days"][key])
            continue
        n = _int(days_in[key])
        if n is None:
            errs.append("“{0}”: số ngày phải là số nguyên.".format(labels[key]))
        elif not C.RULE_DAYS_MIN <= n <= C.RULE_DAYS_MAX:
            errs.append("“{0}”: số ngày từ {1} đến {2}.".format(labels[key], C.RULE_DAYS_MIN, C.RULE_DAYS_MAX))
        else:
            days[key] = n
    mult = {}
    for p in C.PRIORITIES:
        if p not in mult_in or mult_in.get(p) in (None, ""):
            mult[p] = float(active["mult"][p])
            continue
        x = _num(mult_in[p])
        if x is None:
            errs.append("Hệ số “{0}” phải là số (ví dụ 0,5).".format(p))
        elif not C.RULE_MULT_MIN - 1e-9 <= x <= C.RULE_MULT_MAX + 1e-9:
            errs.append("Hệ số “{0}” từ {1} đến {2}.".format(p, fmt_mult(C.RULE_MULT_MIN), fmt_mult(C.RULE_MULT_MAX)))
        elif round(x, 2) != round(x, 6):
            errs.append("Hệ số “{0}” tối đa 2 chữ số thập phân.".format(p))
        else:
            mult[p] = round(x, 2)
    reason = D.clean_text(data.get("reason"), C.RULE_REASON_MAX + 1)
    if len(reason) > C.RULE_REASON_MAX:
        errs.append("Lý do dài quá {0} ký tự.".format(C.RULE_REASON_MAX))
    if errs:
        raise D.Invalid(errs)
    return {"days": days, "mult": mult, "reason": reason}


def diff(old, new):
    """old / new = {days, mult, labels?} -> danh sach thay doi theo thu tu bang quy tac."""
    labels = (new.get("labels") or old.get("labels") or {})
    out = []
    for key, _t, table_label, _d, _n in C.RULE_DEFAULTS:
        a, b = int(old["days"][key]), int(new["days"][key])
        if a != b:
            out.append({"key": key, "label": labels.get(key) or table_label, "kind": "days", "old": a, "new": b,
                        "text": "%s %d → %d ngày" % (labels.get(key) or table_label, a, b)})
    for p in C.PRIORITIES:
        a, b = float(old["mult"][p]), float(new["mult"][p])
        if round(a, 4) != round(b, 4):
            out.append({"key": p, "label": "Hệ số " + p, "kind": "mult", "old": a, "new": b,
                        "text": "Hệ số %s ×%s → ×%s" % (p, fmt_mult(a), fmt_mult(b))})
    return out


def summary(changes, limit=4):
    """"Crawl data mới 5 → 7 ngày; Hệ số Khẩn ×0,5 → ×0,6" (cat bot + "và N thay đổi khác")."""
    if not changes:
        return "Không đổi so với bộ trước"
    head = "; ".join(c["text"] for c in changes[:limit])
    if len(changes) > limit:
        head += "; và %d thay đổi khác" % (len(changes) - limit)
    return head


def to_doc(values, labels):
    """{days, mult} -> truong cua EC Data SLA Rule Set (items + mult_*)."""
    notes = {r[0]: r[4] for r in C.RULE_DEFAULTS}
    out = {"items": [{"rule_key": key, "label": labels.get(key) or table_label, "days": int(values["days"][key]),
                      "note": (values.get("notes") or {}).get(key, notes[key])}
                     for key, _t, table_label, _d, _n in C.RULE_DEFAULTS]}
    for p, field in C.MULT_FIELDS.items():
        out[field] = float(values["mult"][p])
    return out


def view(rule_set):
    """Ban ghi -> rules_view (kem ten / so phien ban)."""
    v = D.rules_view(rule_set)
    v["version_no"] = int((rule_set or {}).get("version_no") or 0)
    return v

# Copyright (c) 2026, eCentric and contributors
"""Dung du lieu cho trang /tai-lieu (THUAN, khong frappe): nhan, ngay, so do theo vai tro."""
import datetime as _dt
import json

from ecentric_workspace.iso_docs import constants as C
from ecentric_workspace.iso_docs import domain as D

#: trang thai luu tren site (co the "Nhap") -> nhan hien thi
_LABELS = {D.norm_state(s): s for s in C.STATES}
TYPE_ORDER = [n for _p, n in C.DOC_TYPES]
TYPE_PLURAL = {"Quy trình": "Quy trình", "Quy định": "Quy định", "Quy chế": "Quy chế",
               "Chính sách": "Chính sách", "Hướng dẫn": "Hướng dẫn", "Biểu mẫu": "Biểu mẫu",
               "Tài liệu hệ thống": "Tài liệu hệ thống"}
PENDING = (C.S_HEAD, C.S_ISO, C.S_CEO, C.S_WITHDRAW)
REVIEW_SOON_DAYS = 30


def state_label(state):
    return _LABELS.get(D.norm_state(state), state or C.S_DRAFT)


def is_pending(state):
    return any(D.is_state(state, s) for s in PENDING)


def dept_label(dept):
    return (dept or "").replace(" - EC", "")


def code_dept(code):
    parts = (code or "").split("-")
    return parts[1] if len(parts) >= 3 and parts[0] != "BM" else (parts[2] if len(parts) >= 4 else "")


def fdate(d):
    if not d:
        return ""
    if isinstance(d, str):
        try:
            d = _dt.date.fromisoformat(d[:10])
        except ValueError:
            return d
    return d.strftime("%d/%m/%Y")


def to_date(d):
    if not d or isinstance(d, _dt.date):
        return d or None
    try:
        return _dt.date.fromisoformat(str(d)[:10])
    except ValueError:
        return None


def review_due(doc, today):
    """'qua-han' / 'sap-den-han' / '' - chi tai lieu dang co phien ban hieu luc."""
    nr = to_date(doc.get("ec_next_review"))
    if not nr or not doc.get("ec_current_version") or D.is_state(doc.get("ec_doc_state"), C.S_EXPIRED):
        return ""
    if nr < today:
        return "qua-han"
    if (nr - today).days <= REVIEW_SOON_DAYS:
        return "sap-den-han"
    return ""


def load_steps(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def flow(steps_raw):
    """-> {facts, roles: [{ma, ten, nodes, work}], steps, forms, form_erp, faq} cho trang tai lieu.

    Vai tro duoc to sang o buoc ma vai tro do la A (chiu trach nhiem) hoac R (thuc hien)."""
    data = load_steps(steps_raw)
    tt = data.get("tom_tat") or {}
    facts = [(lbl, tt.get(k)) for k, lbl in (("dung_khi", "Dùng khi"), ("chuan_bi", "Bạn chuẩn bị"),
                                             ("ket_qua", "Kết quả")) if tt.get(k)]
    names = {r.get("ma"): r.get("ten") or r.get("ma") for r in data.get("vai_tro") or [] if isinstance(r, dict)}
    steps = [dict(b, who=names.get(b.get("A"), b.get("A") or "")) for b in data.get("buoc") or [] if isinstance(b, dict)]
    roles = []
    for r in data.get("vai_tro") or []:
        if not isinstance(r, dict) or not r.get("ma"):
            continue
        mine = [b for b in steps if b.get("A") == r["ma"] or r["ma"] in (b.get("R") or [])]
        if not mine:
            continue
        roles.append({"ma": r["ma"], "ten": r.get("ten") or r["ma"], "nodes": [b.get("id") for b in mine],
                      "work": [{"stt": str(b.get("stt") or ""), "ten": b.get("ten") or "",
                                "dien_giai": b.get("dien_giai") or ""} for b in mine]})
    form_erp = next((b.get("form_erp") for b in steps if (b.get("form_erp") or "").startswith("/")), "")
    return {"facts": facts, "roles": roles, "steps": steps,
            "forms": [f for f in data.get("bieu_mau") or [] if isinstance(f, dict)],
            "form_erp": form_erp, "faq": data.get("cau_hoi_thuong_gap") or []}


def group_by_type(rows):
    out = {}
    for r in rows:
        out.setdefault(r.get("ec_doc_type") or "Khác", []).append(r)
    order = TYPE_ORDER + sorted(k for k in out if k not in TYPE_ORDER)
    return [(TYPE_PLURAL.get(k, k), sorted(out[k], key=lambda x: x.get("ec_doc_code") or ""))
            for k in order if k in out]

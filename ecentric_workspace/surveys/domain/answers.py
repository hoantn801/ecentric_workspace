# Copyright (c) 2026, eCentric and contributors
"""Cau tra loi: duong di qua cac phan, kiem + lam sach, cham diem.

Dinh dang cau tra loi (answers_json) - mot dict {question_id: gia_tri}:
    short_text / paragraph / date / time   chuoi
    single / dropdown / multi              {"sel": [option_id, ...], "other": "chu"}
    scale / rating                         so nguyen
    grid_single                            {row_id: col_id}
    grid_multi                             {row_id: [col_id, ...]}
    ranking                                [option_id theo thu tu uu tien]
    file                                   [{"url": "/private/files/...", "name": "..."}]

SERVER LA NGUON SU THAT. JS cung tinh duong di de biet trang ke tiep (UX), nhung luc nop
server tinh LAI: cau nao nam o phan nguoi dung khong di qua thi bi bo, "bat buoc" chi tinh
tren cac phan da di qua. Tranh truong hop sua JS de nop thieu cau bat buoc.
"""
import datetime
import re

from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.domain import schema

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9 .-]{7,18}[0-9]$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ------------------------------------------------------------------------ duong di --

def _selected(ans):
    if isinstance(ans, dict):
        sel = ans.get("sel")
        if isinstance(sel, list):
            return [str(x) for x in sel]
        if isinstance(sel, str):
            return [sel]
        return []
    if isinstance(ans, str) and ans:
        return [ans]
    return []


def _branch_target(items, answers):
    target = None
    for q in items:
        if q.get("kind") != C.KIND_QUESTION or not q.get("branch"):
            continue
        sel = _selected(answers.get(q["id"]))
        if not sel:
            continue
        for o in q.get("options") or []:
            if o["id"] == sel[0] and o.get("goto"):
                target = o["goto"]          # cau sau cung trong phan quyet dinh (nhu Google)
    return target


def path(form, answers):
    """[section_id] nguoi tra loi di qua, theo thu tu. Chi nhay TOI (khong vong lap)."""
    answers = answers if isinstance(answers, dict) else {}
    secs = schema.sections(form)
    order = {sid: i for i, (sid, _x, _y) in enumerate(secs)}
    out, i = [], 0
    while 0 <= i < len(secs):
        sid, sec, its = secs[i]
        out.append(sid)
        target = _branch_target(its, answers)
        if target is None:
            target = (sec or {}).get("next") or C.GOTO_NEXT
        if target == C.GOTO_SUBMIT:
            break
        j = order.get(target, -1) if target else i + 1
        i = j if j > i else i + 1
    return out


def visible_questions(form, answers):
    seen = set(path(form, answers))
    out = []
    for sid, _sec, its in schema.sections(form):
        if sid in seen:
            out.extend(q for q in its if q.get("kind") == C.KIND_QUESTION)
    return out


# ------------------------------------------------------------------------ lam sach --

def _text(v, limit):
    return ("" if v is None else str(v)).strip()[:limit]


def _check_text(q, val):
    v = q.get("validation") or {}
    kind, lo, hi = v.get("kind"), v.get("min"), v.get("max")
    if kind == C.VALIDATION_NUMBER:
        try:
            num = float(val.replace(",", "."))
        except ValueError:
            return "Cần nhập một con số."
        if lo is not None and num < lo:
            return "Số phải từ %s trở lên." % lo
        if hi is not None and num > hi:
            return "Số phải không quá %s." % hi
    elif kind == C.VALIDATION_EMAIL and not _EMAIL_RE.match(val):
        return "Email không đúng định dạng."
    elif kind == C.VALIDATION_PHONE and not _PHONE_RE.match(val):
        return "Số điện thoại không đúng định dạng."
    elif kind == C.VALIDATION_LENGTH:
        if lo is not None and len(val) < lo:
            return "Cần ít nhất %s ký tự." % lo
        if hi is not None and len(val) > hi:
            return "Tối đa %s ký tự." % hi
    return None


def _choice(q, raw):
    valid = [o["id"] for o in q.get("options") or []]
    sel = []
    for x in _selected(raw):
        if x in valid and x not in sel:
            sel.append(x)
    other = _text(raw.get("other"), C.MAX_SHORT_ANSWER) if isinstance(raw, dict) else ""
    if not q.get("allow_other"):
        other = ""
    if q["type"] in (C.Q_SINGLE, C.Q_DROPDOWN):
        if other:
            sel = []
        sel = sel[:1]
    if not sel and not other:
        return None, None
    out = {"sel": sel}
    if other:
        out["other"] = other
    if q["type"] == C.Q_MULTI:
        n = len(sel) + (1 if other else 0)
        if q.get("min_select") and n < q["min_select"]:
            return out, "Chọn ít nhất %d mục." % q["min_select"]
        if q.get("max_select") and n > q["max_select"]:
            return out, "Chọn tối đa %d mục." % q["max_select"]
    return out, None


def _int_in(raw, lo, hi):
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


def _grid(q, raw):
    if not isinstance(raw, dict):
        return None, None
    rows = [r["id"] for r in q.get("rows") or []]
    cols = {c["id"] for c in q.get("cols") or []}
    out = {}
    for r in rows:
        v = raw.get(r)
        if q["type"] == C.Q_GRID_SINGLE:
            if isinstance(v, str) and v in cols:
                out[r] = v
        else:
            picked = [c for c in (v if isinstance(v, list) else []) if c in cols]
            if picked:
                out[r] = list(dict.fromkeys(picked))
    if not out:
        return None, None
    if q.get("require_each_row") and len(out) < len(rows):
        return out, "Cần trả lời đủ mọi hàng."
    return out, None


def _ranking(q, raw):
    valid = [o["id"] for o in q.get("options") or []]
    if not isinstance(raw, list) or not raw:
        return None, None
    order = [str(x) for x in raw]
    if sorted(order) != sorted(valid):
        return None, "Thứ tự xếp hạng không hợp lệ - tải lại trang rồi thử lại."
    return order, None


def _files(q, raw):
    if not isinstance(raw, list) or not raw:
        return None, None
    out = []
    for f in raw:
        if not isinstance(f, dict):
            continue
        url = _text(f.get("url"), 500)
        if not url.startswith("/private/files/"):
            return None, "Tệp tải lên không hợp lệ."
        out.append({"url": url, "name": _text(f.get("name"), 200) or url.rsplit("/", 1)[-1]})
    if not out:
        return None, None
    if len(out) > (q.get("max_files") or 1):
        return out, "Tối đa %d tệp." % (q.get("max_files") or 1)
    return out, None


def clean_one(q, raw):
    """(gia_tri_sach | None neu bo trong, loi | None)."""
    t = q["type"]
    if t in (C.Q_SHORT, C.Q_PARAGRAPH):
        val = _text(raw, C.MAX_ANSWER if t == C.Q_PARAGRAPH else C.MAX_SHORT_ANSWER)
        if not val:
            return None, None
        return val, _check_text(q, val)
    if t in C.CHOICE_TYPES:
        return _choice(q, raw if isinstance(raw, (dict, str)) else {})
    if t == C.Q_SCALE:
        if raw in (None, ""):
            return None, None
        n = _int_in(raw, q.get("scale_min", 1), q.get("scale_max", 5))
        return (n, None) if n is not None else (None, "Giá trị ngoài thang điểm.")
    if t == C.Q_RATING:
        if raw in (None, "", 0, "0"):
            return None, None
        n = _int_in(raw, 1, q.get("rating_max", 5))
        return (n, None) if n is not None else (None, "Số sao không hợp lệ.")
    if t in C.GRID_TYPES:
        return _grid(q, raw)
    if t == C.Q_RANKING:
        return _ranking(q, raw)
    if t == C.Q_DATE:
        val = _text(raw, 10)
        if not val:
            return None, None
        try:
            if not _DATE_RE.match(val):
                raise ValueError
            datetime.date(int(val[:4]), int(val[5:7]), int(val[8:10]))
        except ValueError:
            return None, "Ngày không hợp lệ."
        return val, None
    if t == C.Q_TIME:
        val = _text(raw, 5)
        if not val:
            return None, None
        return (val, None) if _TIME_RE.match(val) else (None, "Giờ không hợp lệ.")
    if t == C.Q_FILE:
        return _files(q, raw)
    return None, None


def clean(form, raw_answers):
    """(answers_sach, {question_id: loi}). Chi giu cau o cac phan da di qua."""
    raw_answers = raw_answers if isinstance(raw_answers, dict) else {}
    # Duong di tinh tren cau tra loi DA lam sach phan lua chon, de mot option_id gia khong
    # re nhanh duoc.
    out, errors = {}, {}
    for q in visible_questions(form, raw_answers):
        val, err = clean_one(q, raw_answers.get(q["id"]))
        if err:
            errors[q["id"]] = err
        if val is not None:
            out[q["id"]] = val
        elif q.get("required") and not err:
            errors[q["id"]] = "Câu này bắt buộc."
    # Lam sach co the doi duong di (vd option sai bi bo) -> chi giu cau con nhin thay.
    seen = {q["id"] for q in visible_questions(form, out)}
    out = {k: v for k, v in out.items() if k in seen}
    errors = {k: v for k, v in errors.items() if k in seen}
    return out, errors


def first_error(form, errors):
    """Loi dau tien theo thu tu cau hoi, kem so thu tu cau - de bao cho nguoi dung."""
    for n, q in enumerate(schema.questions(form), 1):
        if q["id"] in errors:
            return "Câu %d: %s" % (n, errors[q["id"]])
    return ""


def file_urls(form, answers):
    urls = []
    for q in schema.questions(form):
        if q["type"] == C.Q_FILE:
            urls.extend(f["url"] for f in answers.get(q["id"]) or [])
    return urls


# -------------------------------------------------------------------------- cham diem --

def _is_correct(q, val):
    correct = q.get("correct") or []
    if not correct or val is None:
        return False
    t = q["type"]
    if t == C.Q_SHORT:
        return str(val).strip().lower() in {c.strip().lower() for c in correct}
    if not isinstance(val, dict) or val.get("other"):
        return False
    sel = val.get("sel") or []
    if t == C.Q_MULTI:
        return set(sel) == set(correct)
    return bool(sel) and sel[0] in correct


def score(form, answers):
    """{"score", "max_score", "detail": {qid: true/false}} - chi tinh cau co diem."""
    total = got = 0
    detail = {}
    for q in schema.questions(form):
        pts = q.get("points") or 0
        if not pts or q["type"] not in C.QUIZ_TYPES:
            continue
        total += pts
        ok = _is_correct(q, answers.get(q["id"]))
        detail[q["id"]] = ok
        if ok:
            got += pts
    return {"score": got, "max_score": total, "detail": detail}

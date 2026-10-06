# Copyright (c) 2026, eCentric and contributors
"""form_json: cau truc cau hoi cua mot khao sat.

    {"v": 1, "items": [ <item>, ... ]}

Moi item co `id` on dinh (cau tra loi tro vao id, nen doi thu tu khong lam mat du lieu) va
`kind`:
    section  ngat phan: {title, description, next}      next = "" | <id phan> | "__submit__"
    note     khoi chu:  {title, description}
    question cau hoi:   {type, title, description, required, ...tuy loai}

Hai buoc, co chu dich tach rieng:
  * normalize()        - chay MOI lan luu (ke ca tu luu ban nhap). Chi loc khoa la, cat chuoi,
                         ep kieu, sinh id thieu. Khong bao gio tu choi vi "chua viet xong" -
                         ban nhap duoc phep do dang.
  * publish_problems() - chay luc PHAT HANH. Tra danh sach loi doc duoc ("Cau 3: chua co lua
                         chon nao"). Rong = phat hanh duoc.
"""
import re

from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.domain.errors import SurveyError

SCHEMA_VERSION = 1
START_SECTION = "__start__"            # phan dau tien khi form khong mo dau bang mot section
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


# --------------------------------------------------------------------------- tien ich --

def _s(v, limit):
    return ("" if v is None else str(v)).strip()[:limit]


def _b(v):
    return v in (True, 1, "1", "true", "True", "yes")


def _i(v, default, lo, hi):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


class _Ids:
    """Cap id duy nhat: giu id hop le cua client, sinh id moi khi thieu / trung / sai mau."""

    def __init__(self, prefix):
        self.used, self.prefix, self.n = set(), prefix, 0

    def take(self, raw):
        raw = str(raw or "")
        if _ID_RE.match(raw) and raw not in self.used and raw not in (START_SECTION, C.GOTO_SUBMIT):
            self.used.add(raw)
            return raw
        while True:
            self.n += 1
            cand = "%s%d" % (self.prefix, self.n)
            if cand not in self.used:
                self.used.add(cand)
                return cand


def _options(raw, ids, with_goto):
    out = []
    for o in (raw or [])[:C.MAX_OPTIONS]:
        if not isinstance(o, dict):
            o = {"label": o}
        opt = {"id": ids.take(o.get("id")), "label": _s(o.get("label"), C.MAX_TEXT)}
        if with_goto:
            opt["goto"] = _s(o.get("goto"), 40)
        out.append(opt)
    return out


def _rows(raw, ids):
    out = []
    for o in (raw or [])[:C.MAX_GRID_ROWS]:
        if not isinstance(o, dict):
            o = {"label": o}
        out.append({"id": ids.take(o.get("id")), "label": _s(o.get("label"), C.MAX_TEXT)})
    return out


# ------------------------------------------------------------------------- normalize --

def _question(it, qid):
    qtype = it.get("type") if it.get("type") in C.QUESTION_TYPES else C.Q_SHORT
    q = {"id": qid, "kind": C.KIND_QUESTION, "type": qtype,
         "title": _s(it.get("title"), C.MAX_TEXT),
         "description": _s(it.get("description"), C.MAX_DESC),
         "required": _b(it.get("required")),
         "points": _i(it.get("points"), 0, 0, 100)}
    if qtype in C.OPTION_TYPES:
        branch = qtype in C.BRANCH_TYPES and _b(it.get("branch"))
        q["options"] = _options(it.get("options"), _Ids("o"), branch)
        q["shuffle"] = _b(it.get("shuffle"))
        if qtype in C.BRANCH_TYPES:
            q["branch"] = branch
        if qtype in (C.Q_SINGLE, C.Q_MULTI):
            q["allow_other"] = _b(it.get("allow_other"))
        if qtype == C.Q_MULTI:
            q["min_select"] = _i(it.get("min_select"), 0, 0, C.MAX_OPTIONS)
            q["max_select"] = _i(it.get("max_select"), 0, 0, C.MAX_OPTIONS)
    elif qtype == C.Q_SCALE:
        q["scale_min"] = _i(it.get("scale_min"), 1, C.SCALE_MIN_LOW, 1)
        q["scale_max"] = _i(it.get("scale_max"), 5, 2, C.SCALE_MAX_HIGH)
        q["min_label"] = _s(it.get("min_label"), 60)
        q["max_label"] = _s(it.get("max_label"), 60)
    elif qtype == C.Q_RATING:
        q["rating_max"] = _i(it.get("rating_max"), 5, 3, C.RATING_MAX)
    elif qtype in C.GRID_TYPES:
        q["rows"] = _rows(it.get("rows"), _Ids("r"))
        q["cols"] = _rows(it.get("cols"), _Ids("c"))
        q["require_each_row"] = _b(it.get("require_each_row"))
    elif qtype in (C.Q_SHORT, C.Q_PARAGRAPH):
        v = it.get("validation") if isinstance(it.get("validation"), dict) else {}
        kind = v.get("kind") if v.get("kind") in C.VALIDATIONS else C.VALIDATION_NONE
        if qtype == C.Q_PARAGRAPH and kind not in (C.VALIDATION_NONE, C.VALIDATION_LENGTH):
            kind = C.VALIDATION_NONE
        q["validation"] = {"kind": kind, "min": _num(v.get("min")), "max": _num(v.get("max"))}
    elif qtype == C.Q_FILE:
        q["max_files"] = _i(it.get("max_files"), 1, 1, C.MAX_FILES)
    if qtype in C.QUIZ_TYPES:
        q["correct"] = [_s(x, C.MAX_TEXT) for x in (it.get("correct") or [])
                        if _s(x, C.MAX_TEXT)][:C.MAX_OPTIONS]
        if qtype in C.CHOICE_TYPES:
            valid = {o["id"] for o in q["options"]}
            q["correct"] = [x for x in q["correct"] if x in valid]
    else:
        q["points"] = 0
    return q


def _num(v):
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else f


def normalize(form):
    """Tra ve form sach. Chi nem SurveyError khi du lieu hong ve CAU TRUC (khong phai dict /
    qua gioi han) - ban nhap do dang van luu duoc."""
    if form in (None, ""):
        form = {}
    if not isinstance(form, dict):
        raise SurveyError("Dữ liệu câu hỏi không hợp lệ.")
    raw_items = form.get("items") or []
    if not isinstance(raw_items, list):
        raise SurveyError("Dữ liệu câu hỏi không hợp lệ.")
    if len(raw_items) > C.MAX_ITEMS:
        raise SurveyError("Tối đa %d mục trong một khảo sát." % C.MAX_ITEMS)
    item_ids = _Ids("i")
    items = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        kind = it.get("kind") if it.get("kind") in C.ITEM_KINDS else C.KIND_QUESTION
        iid = item_ids.take(it.get("id"))
        if kind == C.KIND_SECTION:
            items.append({"id": iid, "kind": kind, "title": _s(it.get("title"), C.MAX_TEXT),
                          "description": _s(it.get("description"), C.MAX_DESC),
                          "next": _s(it.get("next"), 40)})
        elif kind == C.KIND_NOTE:
            items.append({"id": iid, "kind": kind, "title": _s(it.get("title"), C.MAX_TEXT),
                          "description": _s(it.get("description"), C.MAX_DESC)})
        else:
            # id lua chon / hang / cot chi can duy nhat TRONG mot cau hoi.
            items.append(_question(it, iid))
    return {"v": SCHEMA_VERSION, "items": items}


# --------------------------------------------------------------------- doc cau truc --

def sections(form):
    """[(section_id, section_item_or_None, [items cua phan])] theo thu tu. Phan dau tien
    khong co item section se mang id START_SECTION."""
    out, cur = [], [START_SECTION, None, []]
    for it in form.get("items") or []:
        if it.get("kind") == C.KIND_SECTION:
            if cur[1] is not None or cur[2]:
                out.append(tuple(cur))
            cur = [it["id"], it, []]
        else:
            cur[2].append(it)
    if cur[1] is not None or cur[2] or not out:
        out.append(tuple(cur))
    return out


def questions(form):
    return [it for it in form.get("items") or [] if it.get("kind") == C.KIND_QUESTION]


def question_map(form):
    return {q["id"]: q for q in questions(form)}


def has_file_question(form):
    return any(q.get("type") == C.Q_FILE for q in questions(form))


# ------------------------------------------------------------------- publish checks --

def _label(n, q):
    return "Câu %d%s" % (n, (" (“%s”)" % q["title"][:40]) if q.get("title") else "")


def publish_problems(form, anonymous=False, quiz=False):
    """Danh sach loi chan phat hanh, tieng Viet, theo thu tu xuat hien. Rong = OK."""
    probs = []
    secs = sections(form)
    order = {sid: i for i, (sid, _s_it, _x) in enumerate(secs)}
    qs = questions(form)
    if not qs:
        return ["Khảo sát chưa có câu hỏi nào."]
    n = 0
    for si, (sid, sec, its) in enumerate(secs):
        if sec is not None:
            nxt = sec.get("next") or ""
            if nxt not in ("", C.GOTO_SUBMIT) and order.get(nxt, -1) <= si:
                probs.append("Phần “%s”: chỉ được chuyển tới một phần NẰM SAU nó."
                             % (sec.get("title") or "không tên"))
        for q in its:
            if q.get("kind") != C.KIND_QUESTION:
                continue
            n += 1
            lb = _label(n, q)
            if not q.get("title"):
                probs.append("Câu %d: chưa có nội dung câu hỏi." % n)
            t = q["type"]
            if t in C.OPTION_TYPES:
                opts = q.get("options") or []
                if not opts:
                    probs.append("%s: chưa có lựa chọn nào." % lb)
                elif any(not o["label"] for o in opts):
                    probs.append("%s: có lựa chọn để trống." % lb)
                labels = [o["label"].lower() for o in opts if o["label"]]
                if len(set(labels)) != len(labels):
                    probs.append("%s: có hai lựa chọn trùng nhau." % lb)
                if q.get("branch"):
                    for o in opts:
                        g = o.get("goto") or ""
                        if g not in ("", C.GOTO_SUBMIT) and order.get(g, -1) <= si:
                            probs.append("%s: lựa chọn “%s” chuyển tới một phần không nằm "
                                         "sau câu hỏi." % (lb, o["label"]))
                if t == C.Q_MULTI and q.get("max_select") and q.get("min_select", 0) > q["max_select"]:
                    probs.append("%s: số lựa chọn tối thiểu lớn hơn tối đa." % lb)
            if t in C.GRID_TYPES and (not q.get("rows") or not q.get("cols")):
                probs.append("%s: lưới cần ít nhất một hàng và một cột." % lb)
            if t in C.GRID_TYPES and any(not r["label"] for r in q.get("rows", []) + q.get("cols", [])):
                probs.append("%s: lưới có hàng/cột để trống." % lb)
            if t == C.Q_FILE and anonymous:
                probs.append("%s: khảo sát ẩn danh không dùng được câu tải tệp (tệp lộ người gửi)."
                             % lb)
            v = q.get("validation") or {}
            if v.get("min") is not None and v.get("max") is not None and v["min"] > v["max"]:
                probs.append("%s: giới hạn nhỏ nhất lớn hơn lớn nhất." % lb)
            if quiz and q.get("points") and not q.get("correct"):
                probs.append("%s: có điểm nhưng chưa chọn đáp án đúng." % lb)
    return probs

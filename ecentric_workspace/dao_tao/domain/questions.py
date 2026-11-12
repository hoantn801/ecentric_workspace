# Copyright (c) 2026, eCentric and contributors
"""10 kieu cau hoi: chuan hoa khi soan, ban "cong khai" gui may nguoi choi, chuan hoa cau
tra loi, cham. Thuan Python - khong import frappe.

BIEN GIOI CHONG GIAN LAN: `public_view()` la ham DUY NHAT tao du lieu cau hoi gui xuong may
nguoi choi truoc khi cau khoa. No KHONG BAO GIO chua: correct, answer/tolerance cua thanh
truot, vung dung cua ghim, thu tu dung cua sap xep, cap dung cua ghep cap, dap an go chu.
Ma (id) cua lua chon / muc duoc SINH NGAU NHIEN moi lan luu (`rid`), nen id khong lo thu tu
dung (vd "o1" luon la dap an dung vi nguoi soan hay de dap an dung o A).

Dang luu (questions_json cua EC Quiz):
  chung: id, type, text, time (giay), media {kind, url} | None, explain
  single/multi/poll: options [{id, text}], correct [id...]   (poll: correct = [])
  truefalse:         options [{id:"t"},{id:"f"}], correct ["t"|"f"]
  slider:            min, max, step, answer, tolerance, unit
  pin:               media (anh, bat buoc), zone {shape: rect, x, y, w, h} | {shape: circle, x, y, r}
                     (toa do 0..1 theo be ngang / be doc anh)
  order:             items [{id, text}] theo THU TU DUNG
  match:             pairs [{id, left, rid, right}]  (id = ve trai, rid = ve phai)
  type:              accept ["cach viet 1", ...]
  cloud:             (khong co gi them)
Cau tra loi (tu may nguoi choi):
  single/poll/truefalse {"o": id} · multi {"o": [id]} · slider {"v": so} · pin {"x", "y"}
  order {"o": [id theo thu tu]} · match {"m": {id_trai: rid_phai}} · type/cloud {"t": "chu"}
"""
import hashlib
import random
import re
import unicodedata

from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.domain.errors import FieldErrors, QuizError

TF_TRUE, TF_FALSE = "t", "f"
TF_OPTIONS = [{"id": TF_TRUE, "text": "Đúng"}, {"id": TF_FALSE, "text": "Sai"}]
TYPE_LABELS = {C.Q_SINGLE: "Trắc nghiệm", C.Q_MULTI: "Chọn nhiều", C.Q_TRUEFALSE: "Đúng / Sai",
               C.Q_SLIDER: "Thanh trượt", C.Q_PIN: "Ghim trên ảnh", C.Q_ORDER: "Sắp xếp",
               C.Q_MATCH: "Ghép cặp", C.Q_TYPE: "Gõ đáp án", C.Q_POLL: "Bình chọn",
               C.Q_CLOUD: "Đám mây từ"}


_RID = re.compile(r"^[0-9a-f]{6}$")


def _keep(v, rid):
    """Giu id cu neu la id do server sinh (6 ky tu hex) - luu lai bo quiz khong lam hong bai
    nguoi hoc dang lam do (QA 12/11). Id moi / id tam cua trinh soan ("n1") -> sinh moi."""
    return v if isinstance(v, str) and _RID.match(v) else rid()


def default_rid():
    return "%06x" % random.SystemRandom().getrandbits(24)


def _text(v, limit):
    s = re.sub(r"\s+", " ", str(v if v is not None else "")).strip()
    return s[:limit]


def _num(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f or f in (float("inf"), float("-inf")):
        return default
    return f


def _clean_media(m):
    if not isinstance(m, dict):
        return None
    url = _text(m.get("url"), 500)
    kind = m.get("kind") if m.get("kind") in C.MEDIA_KINDS else C.MEDIA_IMAGE
    if not url:
        return None
    # Chi nhan tep cua chinh site (/files/...) hoac https - khong javascript:, data:, http:.
    if not (url.startswith("/files/") or url.startswith("/private/files/")
            or url.startswith("https://")):
        return None
    return {"kind": kind, "url": url}


def _clean_items(raw, limit, rid, key="text"):
    out = []
    for it in raw or []:
        t = _text(it.get(key) if isinstance(it, dict) else it, C.MAX_OPTION_TEXT)
        if t:
            src = it.get("id") if isinstance(it, dict) else None
            out.append({"id": _keep(src, rid), "text": t, "_src": src})
    return out[:limit]


def _unique_ids(q, rid):
    """Chong trung id ngau nhien (xac suat rat nho, nhung trung la cham sai)."""
    if q["type"] == C.Q_TRUEFALSE:
        return                                   # id co dinh "t" / "f"
    seen = {TF_TRUE, TF_FALSE}
    for key in ("options", "items"):
        for it in q.get(key) or []:
            while it["id"] in seen:
                it["id"] = rid()
            seen.add(it["id"])
    for p in q.get("pairs") or []:
        for k in ("id", "rid"):
            while p[k] in seen:
                p[k] = rid()
            seen.add(p[k])


def clean_question(raw, rid=default_rid):
    """dict tu trinh soan -> (cau da chuan hoa, loi | None)."""
    if not isinstance(raw, dict):
        return None, "Câu hỏi không hợp lệ."
    qt = raw.get("type")
    if qt not in C.QUESTION_TYPES:
        return None, "Chưa chọn kiểu câu."
    text = _text(raw.get("text"), C.MAX_TEXT)
    t = int(_num(raw.get("time"), C.TIME_DEFAULT))
    q = {"id": _keep(raw.get("id"), rid), "type": qt, "text": text,
         "time": t if t in C.TIME_CHOICES else C.TIME_DEFAULT,
         "media": _clean_media(raw.get("media")), "explain": _text(raw.get("explain"), C.MAX_EXPLAIN)}
    if not text:
        return q, "Câu hỏi đang trống."
    if qt in C.OPTION_TYPES:
        opts = _clean_items(raw.get("options"), C.MAX_OPTIONS, rid)
        if len(opts) < C.MIN_OPTIONS:
            q["options"] = [{"id": o["id"], "text": o["text"]} for o in opts]
            q["correct"] = []
            return q, "Cần ít nhất %d lựa chọn." % C.MIN_OPTIONS
        want = raw.get("correct") or []
        want = want if isinstance(want, list) else [want]
        # Trinh soan gui correct theo id CU hoac theo vi tri (so) - doi sang id moi.
        correct = []
        for i, o in enumerate(opts):
            if o["_src"] in want or i in want or str(i) in [str(w) for w in want]:
                correct.append(o["id"])
        for o in opts:
            o.pop("_src", None)
        q["options"] = opts
        q["correct"] = [] if qt == C.Q_POLL else correct
        if qt == C.Q_SINGLE and len(correct) != 1:
            return q, "Trắc nghiệm cần đúng 1 đáp án đúng."
        if qt == C.Q_MULTI and not correct:
            return q, "Chọn nhiều cần ít nhất 1 đáp án đúng."
    elif qt == C.Q_TRUEFALSE:
        val = raw.get("correct")
        val = val[0] if isinstance(val, list) and val else val
        if val in (True, "true", TF_TRUE, 1, "1"):
            q["correct"] = [TF_TRUE]
        elif val in (False, "false", TF_FALSE, 0, "0"):
            q["correct"] = [TF_FALSE]
        else:
            return q, "Chọn Đúng hoặc Sai làm đáp án."
        q["options"] = [dict(o) for o in TF_OPTIONS]
    elif qt == C.Q_SLIDER:
        lo, hi = _num(raw.get("min"), 0), _num(raw.get("max"), 100)
        step = _num(raw.get("step"), 1) or 1
        ans, tol = _num(raw.get("answer")), abs(_num(raw.get("tolerance"), 0))
        q.update({"min": lo, "max": hi, "step": abs(step), "answer": ans, "tolerance": tol,
                  "unit": _text(raw.get("unit"), 12)})
        if hi <= lo:
            return q, "Giá trị lớn nhất phải lớn hơn nhỏ nhất."
        if (hi - lo) / abs(step) > 100000:
            return q, "Bước nhảy quá nhỏ so với khoảng giá trị."
        if ans is None or ans < lo or ans > hi:
            return q, "Đáp án phải nằm trong khoảng %s – %s." % (_fmt(lo), _fmt(hi))
    elif qt == C.Q_PIN:
        z = raw.get("zone") if isinstance(raw.get("zone"), dict) else {}
        shape = z.get("shape") if z.get("shape") in (C.PIN_RECT, C.PIN_CIRCLE) else C.PIN_RECT
        f = lambda k, d=0.0: min(max(_num(z.get(k), d), 0.0), 1.0)  # noqa: E731
        ar = _num(z.get("ar"), 1.0) or 1.0
        zone = ({"shape": shape, "x": f("x"), "y": f("y"), "w": f("w"), "h": f("h")}
                if shape == C.PIN_RECT else {"shape": shape, "x": f("x"), "y": f("y"), "r": f("r"),
                                             # ar = cao / ngang cua anh: r tinh theo be NGANG, truc doc
                                             # phai nhan ar thi vong tron moi tron that tren anh.
                                             "ar": min(max(ar, 0.05), 20.0)})
        q["zone"] = zone
        if not q["media"] or q["media"]["kind"] != C.MEDIA_IMAGE:
            return q, "Ghim trên ảnh cần một ảnh."
        if (shape == C.PIN_RECT and (zone["w"] <= 0 or zone["h"] <= 0)) or \
           (shape == C.PIN_CIRCLE and zone["r"] <= 0):
            return q, "Chưa vẽ vùng đúng trên ảnh."
    elif qt == C.Q_ORDER:
        items = _clean_items(raw.get("items"), C.MAX_ORDER_ITEMS, rid)
        for it in items:
            it.pop("_src", None)
        q["items"] = items
        if len(items) < 3:
            return q, "Sắp xếp cần ít nhất 3 mục."
    elif qt == C.Q_MATCH:
        pairs = []
        for p in (raw.get("pairs") or [])[:C.MAX_MATCH_PAIRS]:
            if not isinstance(p, dict):
                continue
            left, right = _text(p.get("left"), C.MAX_OPTION_TEXT), _text(p.get("right"), C.MAX_OPTION_TEXT)
            if left and right:
                pairs.append({"id": _keep(p.get("id"), rid), "left": left, "rid": _keep(p.get("rid"), rid),
                              "right": right})
        q["pairs"] = pairs
        if len(pairs) < 2:
            return q, "Ghép cặp cần ít nhất 2 cặp."
    elif qt == C.Q_TYPE:
        acc = []
        for a in (raw.get("accept") or [])[:C.MAX_TYPE_ACCEPT]:
            a = _text(a, C.MAX_TYPE_ANSWER)
            if a and norm_text(a) not in [norm_text(x) for x in acc]:
                acc.append(a)
        q["accept"] = acc
        if not acc:
            return q, "Cần ít nhất một đáp án được chấp nhận."
    _unique_ids(q, rid)
    return q, None


def clean_questions(raw_list, rid=default_rid):
    if not isinstance(raw_list, list):
        raise QuizError("Danh sách câu hỏi không hợp lệ.")
    if len(raw_list) > C.MAX_QUESTIONS:
        raise QuizError("Tối đa %d câu một bộ quiz." % C.MAX_QUESTIONS)
    out, errs = [], {}
    for i, raw in enumerate(raw_list):
        q, err = clean_question(raw, rid)
        if err:
            errs["q%d" % (i + 1)] = err
        if q:
            out.append(q)
    return out, errs


def require_valid(raw_list, rid=default_rid):
    qs, errs = clean_questions(raw_list, rid)
    if errs:
        raise FieldErrors("Còn %d câu chưa xong." % len(errs), errs)
    if not qs:
        raise FieldErrors("Bộ quiz chưa có câu nào.", {"q1": "Thêm ít nhất một câu."})
    return qs


def _fmt(n):
    return ("%d" % n) if float(n).is_integer() else ("%s" % n)


# --------------------------------------------------------------------------- xao --

def perm(seed, n):
    """Hoan vi on dinh cua range(n) theo `seed` (chuoi). Cung seed -> cung thu tu (F5 khong doi)."""
    r = random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16))
    idx = list(range(n))
    r.shuffle(idx)
    return idx


def _shuffled(items, seed):
    return [items[i] for i in perm(seed, len(items))]


def secret_seed(secret, *parts):
    """Hat giong xao = HMAC(bi mat phia server, ...). PHAI bi mat: perm() tat dinh, biet hat giong
    la dao nguoc duoc hoan vi -> ra thu tu dung cua cau Sap xep / cap dung cua Ghep cap (QA 12/11)."""
    import hmac
    msg = "|".join(str(p) for p in parts).encode("utf-8")
    return hmac.new(str(secret or "").encode("utf-8"), msg, hashlib.sha256).hexdigest()


def public_view(q, seed, shuffle_options=True):
    """Cau hoi cho may nguoi choi / may chieu - KHONG chua dap an.
    seed: hat giong BI MAT (secret_seed). Sap xep + Ghep cap LUON xao theo seed (thu tu goc chinh
    la dap an). shuffle_options=False: lua chon giu thu tu goc (che do "chi o mau" / may chieu -
    moi nguoi nhin cung thu tu)."""
    if not seed:
        raise QuizError("Thiếu hạt giống xáo.")
    v = {"id": q["id"], "type": q["type"], "text": q["text"], "time": q["time"],
         "media": q.get("media"), "label": TYPE_LABELS.get(q["type"], "")}
    qt = q["type"]
    sh = (lambda items, k: _shuffled(items, "%s|%s" % (seed, k))) if shuffle_options else (lambda items, k: items)
    if qt in C.OPTION_TYPES:
        v["options"] = [{"id": o["id"], "text": o["text"]} for o in sh(q["options"], "o")]
    elif qt == C.Q_TRUEFALSE:
        v["options"] = [dict(o) for o in TF_OPTIONS]
    elif qt == C.Q_SLIDER:
        v.update({k: q[k] for k in ("min", "max", "step", "unit")})
    elif qt == C.Q_ORDER:
        # Luon xao (ke ca khong co seed): thu tu goc CHINH LA dap an.
        v["items"] = [{"id": i["id"], "text": i["text"]}
                      for i in _shuffled(q["items"], "%s|i|%s" % (seed, q["id"]))]
        if [i["id"] for i in v["items"]] == [i["id"] for i in q["items"]]:
            v["items"] = v["items"][1:] + v["items"][:1]
    elif qt == C.Q_MATCH:
        v["lefts"] = [{"id": p["id"], "text": p["left"]} for p in q["pairs"]]
        v["rights"] = [{"id": p["rid"], "text": p["right"]}
                       for p in _shuffled(q["pairs"], "%s|r|%s" % (seed, q["id"]))]
    elif qt == C.Q_TYPE:
        v["maxlen"] = C.MAX_TYPE_ANSWER
    elif qt == C.Q_CLOUD:
        v["maxlen"] = C.MAX_CLOUD_ANSWER
    return v


def reveal_view(q):
    """Dap an + giai thich - CHI gui khi cau da khoa (pha reveal tro di)."""
    out = {"id": q["id"], "type": q["type"], "explain": q.get("explain") or ""}
    qt = q["type"]
    if qt in (C.Q_SINGLE, C.Q_MULTI, C.Q_TRUEFALSE):
        out["correct"] = list(q.get("correct") or [])
    elif qt == C.Q_SLIDER:
        out.update({"answer": q["answer"], "tolerance": q["tolerance"]})
    elif qt == C.Q_PIN:
        out["zone"] = dict(q["zone"])
    elif qt == C.Q_ORDER:
        out["order"] = [i["id"] for i in q["items"]]
    elif qt == C.Q_MATCH:
        out["pairs"] = {p["id"]: p["rid"] for p in q["pairs"]}
    elif qt == C.Q_TYPE:
        out["accept"] = list(q["accept"])
    return out


# ---------------------------------------------------------------- cau tra loi --

def strip_marks(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def norm_text(s, marks=True):
    s = unicodedata.normalize("NFC", str(s or "")).lower().strip()
    s = re.sub(r"\s+", " ", s).strip(" .,!?;:\"'")
    return strip_marks(s) if not marks else s


def clean_answer(q, raw):
    """Cau tra loi tu may -> dang chuan, hoac QuizError neu sai dang (khong chap nhan "rac")."""
    if not isinstance(raw, dict):
        raise QuizError("Câu trả lời không hợp lệ.")
    qt = q["type"]
    if qt in (C.Q_SINGLE, C.Q_POLL, C.Q_TRUEFALSE):
        ids = [o["id"] for o in q["options"]]
        if not isinstance(raw.get("o"), str) or raw.get("o") not in ids:
            raise QuizError("Chưa chọn đáp án.")
        return {"o": raw["o"]}
    if qt == C.Q_MULTI:
        ids = [o["id"] for o in q["options"]]
        got = raw.get("o")
        if not isinstance(got, list) or not got or any(not isinstance(x, str) or x not in ids for x in got):
            raise QuizError("Chưa chọn đáp án.")
        return {"o": sorted(set(got))}
    if qt == C.Q_SLIDER:
        v = _num(raw.get("v"))
        if v is None:
            raise QuizError("Chưa chọn giá trị.")
        return {"v": min(max(v, q["min"]), q["max"])}
    if qt == C.Q_PIN:
        x, y = _num(raw.get("x")), _num(raw.get("y"))
        if x is None or y is None or not (0 <= x <= 1 and 0 <= y <= 1):
            raise QuizError("Chưa ghim lên ảnh.")
        return {"x": round(x, 4), "y": round(y, 4)}
    if qt == C.Q_ORDER:
        ids = [i["id"] for i in q["items"]]
        got = raw.get("o")
        if not isinstance(got, list) or any(not isinstance(x, str) for x in got) or sorted(got) != sorted(ids):
            raise QuizError("Thứ tự không hợp lệ.")
        return {"o": list(got)}
    if qt == C.Q_MATCH:
        m = raw.get("m")
        lefts = {p["id"] for p in q["pairs"]}
        rights = {p["rid"] for p in q["pairs"]}
        if not isinstance(m, dict) or not m:
            raise QuizError("Chưa ghép cặp nào.")
        out = {}
        for k, val in m.items():
            if k not in lefts or not isinstance(val, str) or val not in rights:
                raise QuizError("Ghép cặp không hợp lệ.")
            out[k] = val
        if len(set(out.values())) != len(out):
            raise QuizError("Mỗi mục bên phải chỉ ghép một lần.")
        return {"m": out}
    if qt in (C.Q_TYPE, C.Q_CLOUD):
        limit = C.MAX_TYPE_ANSWER if qt == C.Q_TYPE else C.MAX_CLOUD_ANSWER
        t = _text(raw.get("t"), limit) if isinstance(raw.get("t"), str) else ""
        if not t:
            raise QuizError("Chưa nhập câu trả lời.")
        return {"t": t}
    raise QuizError("Kiểu câu không hỗ trợ.")


def grade(q, ans):
    """-> ti le dung 0..1 (1 = dung tron), hoac None voi kieu khong cham (binh chon, dam may)."""
    qt = q["type"]
    if qt in C.UNSCORED_TYPES:
        return None
    if ans is None:
        return 0.0
    if qt in (C.Q_SINGLE, C.Q_TRUEFALSE):
        return 1.0 if ans.get("o") in (q.get("correct") or []) else 0.0
    if qt == C.Q_MULTI:
        return 1.0 if sorted(ans.get("o") or []) == sorted(q.get("correct") or []) else 0.0
    if qt == C.Q_SLIDER:
        d = abs(float(ans["v"]) - float(q["answer"]))
        tol = float(q.get("tolerance") or 0)
        if d <= tol + 1e-9:
            return 1.0
        # Vung "mot phan": tu tol toi SPAN * max(tol, step) - giam tuyen tinh tu 0.5 ve 0.
        edge = C.SLIDER_PARTIAL_SPAN * max(tol, float(q.get("step") or 1))
        if d >= edge:
            return 0.0
        return round(0.5 * (edge - d) / (edge - tol), 4)
    if qt == C.Q_PIN:
        return 1.0 if in_zone(q["zone"], ans["x"], ans["y"]) else 0.0
    if qt == C.Q_ORDER:
        return 1.0 if ans.get("o") == [i["id"] for i in q["items"]] else 0.0
    if qt == C.Q_MATCH:
        right = {p["id"]: p["rid"] for p in q["pairs"]}
        ok = sum(1 for k, v in (ans.get("m") or {}).items() if right.get(k) == v)
        return round(ok / float(len(right)), 4) if right else 0.0
    if qt == C.Q_TYPE:
        got = ans.get("t") or ""
        if norm_text(got) in [norm_text(a) for a in q["accept"]]:
            return 1.0
        # Go tren dien thoai hay thieu dau: "khong dau" van tinh dung.
        return 1.0 if norm_text(got, False) in [norm_text(a, False) for a in q["accept"]] else 0.0
    return 0.0


def in_zone(zone, x, y):
    if zone.get("shape") == C.PIN_CIRCLE:
        ar = float(zone.get("ar") or 1.0)
        return (x - zone["x"]) ** 2 + ((y - zone["y"]) * ar) ** 2 <= zone["r"] ** 2 + 1e-9
    return zone["x"] - 1e-9 <= x <= zone["x"] + zone["w"] + 1e-9 and \
        zone["y"] - 1e-9 <= y <= zone["y"] + zone["h"] + 1e-9


def tally(q, answers):
    """Tong hop cau tra loi cho may chieu (sau khi khoa): % moi lua chon / dam may tu / ..."""
    qt = q["type"]
    n = len(answers)
    out = {"total": n}
    if qt in C.OPTION_TYPES or qt == C.Q_TRUEFALSE:
        counts = {o["id"]: 0 for o in q["options"]}
        for a in answers:
            for oid in (a["o"] if isinstance(a.get("o"), list) else [a.get("o")]):
                if oid in counts:
                    counts[oid] += 1
        out["options"] = counts
    elif qt == C.Q_CLOUD:
        words = {}
        for a in answers:
            k = norm_text(a.get("t"))
            if k:
                words[k] = words.get(k, 0) + 1
        out["words"] = sorted(words.items(), key=lambda kv: (-kv[1], kv[0]))[:40]
    elif qt == C.Q_SLIDER:
        out["values"] = sorted(a["v"] for a in answers if "v" in a)[:500]
    elif qt == C.Q_PIN:
        out["pins"] = [[a["x"], a["y"]] for a in answers if "x" in a][:500]
    return out

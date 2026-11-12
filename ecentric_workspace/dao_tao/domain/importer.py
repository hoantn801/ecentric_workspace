# Copyright (c) 2026, eCentric and contributors
"""Nhap cau hoi tu Excel theo mau Kahoot hoac Wayground (Quizizz). Thuan Python: nhan cac
dong da doc tu file (list cac list o), tra ve list cau "tho" de dua qua questions.clean_questions.

Kahoot:    Question | Answer 1..4 | Time limit (sec) | Correct answer(s) ("1" / "1,3")
Wayground: Question Text | Question Type | Option 1..5 | Correct Answer | Time in seconds |
           Image Link | Answer explanation
Tim dong tieu de bang chu "Question" o o dau tien co chu (mau that co vai dong huong dan o tren).
"""
import re

from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.domain.errors import QuizError

_WG_TYPES = {"multiple choice": C.Q_SINGLE, "checkbox": C.Q_MULTI, "poll": C.Q_POLL,
             "fill-in-the-blank": C.Q_TYPE, "fill in the blank": C.Q_TYPE,
             "open-ended": C.Q_CLOUD, "open ended": C.Q_CLOUD, "word cloud": C.Q_CLOUD}


def _s(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _idx_list(v):
    return [int(x) - 1 for x in re.findall(r"\d+", _s(v))]


def _time(v):
    try:
        t = int(float(_s(v)))
    except (ValueError, OverflowError):
        return C.TIME_DEFAULT
    return min(C.TIME_CHOICES, key=lambda c: abs(c - t))


def _header(rows):
    for i, r in enumerate(rows[:40]):
        cells = [_s(c).lower() for c in r]
        first = next((c for c in cells if c), "")
        if first.startswith("question"):
            return i, cells
    raise QuizError("Không thấy dòng tiêu đề “Question” - file có đúng mẫu Kahoot / Wayground không?")


def _col(cells, *names):
    for n in names:
        for i, c in enumerate(cells):
            if c.startswith(n):
                return i
    return None


def parse(rows):
    rows = [list(r) for r in (rows or [])]
    hi, cells = _header(rows)
    get = lambda r, i: _s(r[i]) if i is not None and i < len(r) else ""  # noqa: E731
    out = []
    if _col(cells, "question type") is not None:           # Wayground
        qc, tc = _col(cells, "question text", "question"), _col(cells, "question type")
        opts = [_col(cells, "option %d" % n) for n in range(1, 6)]
        cc, timec = _col(cells, "correct answer"), _col(cells, "time")
        imgc, expc = _col(cells, "image link", "image"), _col(cells, "answer explanation", "explanation")
        for r in rows[hi + 1:]:
            text = get(r, qc)
            if not text:
                continue
            qt = _WG_TYPES.get(get(r, tc).lower(), C.Q_SINGLE)
            options = [get(r, i) for i in opts]
            q = {"type": qt, "text": text, "time": _time(get(r, timec)), "explain": get(r, expc)}
            img = get(r, imgc)
            if img.startswith("https://"):
                q["media"] = {"kind": C.MEDIA_IMAGE, "url": img}
            if qt == C.Q_TYPE:
                q["accept"] = [o for o in options if o]
            elif qt in (C.Q_SINGLE, C.Q_MULTI, C.Q_POLL):
                keep = [i for i, o in enumerate(options) if o]
                q["options"] = [{"text": options[i]} for i in keep]
                want = _idx_list(get(r, cc))
                q["correct"] = [keep.index(i) for i in want if i in keep]
            out.append(q)
    else:                                                   # Kahoot
        qc = _col(cells, "question")
        ans = [_col(cells, "answer %d" % n) for n in range(1, 5)]
        timec, cc = _col(cells, "time limit", "time"), _col(cells, "correct")
        for r in rows[hi + 1:]:
            text = get(r, qc)
            if not text:
                continue
            options = [get(r, i) for i in ans]
            keep = [i for i, o in enumerate(options) if o]
            want = [keep.index(i) for i in _idx_list(get(r, cc)) if i in keep]
            low = [options[i].lower() for i in keep]
            if len(keep) == 2 and sorted(low) in (["false", "true"], ["sai", "đúng"]) and len(want) == 1:
                is_true = low[want[0]] in ("true", "đúng")
                out.append({"type": C.Q_TRUEFALSE, "text": text, "time": _time(get(r, timec)),
                            "correct": "t" if is_true else "f"})
                continue
            out.append({"type": C.Q_MULTI if len(want) > 1 else C.Q_SINGLE, "text": text,
                        "time": _time(get(r, timec)),
                        "options": [{"text": options[i]} for i in keep], "correct": want})
    if not out:
        raise QuizError("File không có câu hỏi nào bên dưới dòng tiêu đề.")
    return out[:C.MAX_QUESTIONS]

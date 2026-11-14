# Copyright (c) 2026, eCentric and contributors
"""Bai hoc (huong D: Hoc · Bai hoc · Quan ly bai hoc · Binh chon). Thuan Python.

Noi dung bai luu CHU THUAN (khong HTML): trang tu thoat ky tu + tu noi link + xuong dong. Lam
vay de khong ai chen script vao trang ma ca cong ty mo.
Tien do 1 bai: Xem bai -> Lam quiz (neu co) -> Nop bai thuc hanh (neu co) -> Xem lai.
Quiz bai hoc la tu luyen: nop ca bai, cham mot lan, dung tu 60% duoc 1 ve (lan dau dat).
Bai thuc hanh: cap ve ngay khi nop; Ban dao tao kiem tra ngau nhien va co the thu hoi.
"""
import re

from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.domain import questions as Q
from ecentric_workspace.dao_tao.domain.errors import FieldErrors, QuizError

STEP_VIEW = "view"
STEP_QUIZ = "quiz"
STEP_PRACTICE = "practice"
STEP_DONE = "done"
STEP_LABELS = {STEP_VIEW: "Xem bài", STEP_QUIZ: "Làm quiz", STEP_PRACTICE: "Nộp bài thực hành",
               STEP_DONE: "Xem lại"}


def _t(v, n):
    return re.sub(r"[ \t]+", " ", str(v if v is not None else "")).strip()[:n]


def _url(v):
    u = _t(v, 500)
    if not u:
        return ""
    if u.startswith("https://") or u.startswith("/files/") or u.startswith("/private/files/"):
        return u
    raise QuizError("Link phải bắt đầu bằng https:// hoặc là tệp đã tải lên.")


def clean_lesson(raw):
    raw = raw if isinstance(raw, dict) else {}
    errs = {}
    out = {
        "title": _t(raw.get("title"), 140),
        "summary": _t(raw.get("summary"), 400),
        "body": str(raw.get("body") or "").replace("\r\n", "\n")[:C.MAX_LESSON_TEXT],
        "topic": raw.get("topic") if raw.get("topic") in C.TOPIC_TAGS else C.TOPIC_TAGS[-1],
        "level": raw.get("level") if raw.get("level") in C.LEVELS else C.LEVELS[0],
        "tool": raw.get("tool") if raw.get("tool") in C.TOOL_TAGS else C.TOOL_TAGS[0],
        "quiz": _t(raw.get("quiz"), 140) or None,
        "practice_prompt": _t(raw.get("practice_prompt"), 1000),
        "week_start": _t(raw.get("week_start"), 10) or None,
        "practice_due": _t(raw.get("practice_due"), 19) or None,
    }
    for k in ("video_url", "slide_url"):
        try:
            out[k] = _url(raw.get(k))
        except QuizError as e:
            errs[k] = str(e)
    if not out["title"]:
        errs["title"] = "Bài học cần tiêu đề."
    if out["week_start"] and not re.match(r"^\d{4}-\d{2}-\d{2}$", out["week_start"]):
        errs["week_start"] = "Ngày không hợp lệ."
    if errs:
        raise FieldErrors("Còn thông tin chưa đúng.", errs)
    return out


def step(lesson, progress):
    p = progress or {}
    if not p.get("viewed_at"):
        return STEP_VIEW
    if lesson.get("quiz") and p.get("quiz_score") in (None, ""):
        return STEP_QUIZ
    if lesson.get("practice_prompt") and not p.get("practice_at"):
        return STEP_PRACTICE
    return STEP_DONE


def grade_self_quiz(questions, raw_answers):
    """Quiz tu luyen: -> {score: so cau dung, scored: so cau cham, ratio, detail: [...]}.
    Cau bo trong tinh sai. Tra ve dap an tung cau - nop xong moi xem duoc."""
    raw_answers = raw_answers if isinstance(raw_answers, dict) else {}
    detail, score, scored = [], 0, 0
    for q in questions:
        ans, ratio = None, None
        if q["id"] in raw_answers:
            try:
                ans = Q.clean_answer(q, raw_answers[q["id"]])
            except QuizError:
                ans = None
        ratio = Q.grade(q, ans)
        if ratio is not None:
            scored += 1
            score += 1 if ratio >= 1 else 0
        detail.append({"id": q["id"], "ratio": ratio, "reveal": Q.reveal_view(q)})
    return {"score": score, "scored": scored,
            "ratio": round(score / float(scored), 4) if scored else 0.0, "detail": detail}


def passed(ratio):
    return ratio >= C.PASS_RATIO - 1e-9


def clean_practice(text, link):
    text = str(text or "").strip()[:C.MAX_PRACTICE]
    link = _url(link) if link else ""
    if len(text) < 20 and not link:
        raise QuizError("Bài thực hành cần ít nhất vài câu mô tả (từ 20 ký tự) hoặc một link.")
    return text, link


def clean_topic(raw):
    raw = raw if isinstance(raw, dict) else {}
    title = _t(raw.get("title"), 120)
    if len(title) < 5:
        raise QuizError("Chủ đề cần ít nhất 5 ký tự.")
    return {"title": title, "description": _t(raw.get("description"), 500)}


def votes_left(my_votes_on_open_topics):
    return max(0, C.VOTES_PER_USER - int(my_votes_on_open_topics or 0))

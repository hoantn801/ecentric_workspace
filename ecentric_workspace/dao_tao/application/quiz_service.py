# Copyright (c) 2026, eCentric and contributors
"""Soan bo quiz (trang /quiz/soan) + nhap tu Excel. Chi Ban dao tao / HR / admin (access.py)."""
from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.application.access import require_found, require_host
from ecentric_workspace.dao_tao.domain import importer, prizes, questions as Q, settings
from ecentric_workspace.dao_tao.domain.errors import FieldErrors, QuizError

#: 4 mau nhanh (mockup F1) - chi dat san luat choi, cau hoi tu soan / nhap.
TEMPLATES = {
    "after_class": {"label": "Sau buổi học", "settings": {"mode": C.MODE_SOLO, "board": C.BOARD_EACH}},
    "warmup": {"label": "Khởi động 5 phút", "settings": {"mode": C.MODE_SOLO, "board": C.BOARD_END,
                                                          "by_speed": True}},
    "team_race": {"label": "Thi đua phòng ban", "settings": {"mode": C.MODE_TEAM, "board": C.BOARD_EACH}},
    "self_paced": {"label": "Tự luyện cả tuần", "settings": {"mode": C.MODE_SOLO, "board": C.BOARD_END,
                                                              "by_speed": False}},
}


def _view(quiz):
    return {"name": quiz["name"], "title": quiz["title"], "description": quiz["description"],
            "status": quiz["status"], "template": quiz["template"], "modified": quiz["modified"],
            "questions": quiz["questions"], "settings": settings.clean_settings(quiz["settings"]),
            "prizes": prizes.clean_prizes(quiz["prizes"])}


def meta():
    """Danh muc cho trinh soan (khong co du lieu rieng tu)."""
    return {"types": [{"type": t, "label": Q.TYPE_LABELS[t], "scored": t not in C.UNSCORED_TYPES}
                      for t in C.QUESTION_TYPES],
            "times": list(C.TIME_CHOICES), "time_default": C.TIME_DEFAULT,
            "templates": [{"key": k, "label": v["label"]} for k, v in TEMPLATES.items()],
            "ranks": [{"scope": C.SCOPE_PLAYER, "rank": r, "label": C.RANK_LABELS[r]} for r in C.PLAYER_RANKS] +
                     [{"scope": C.SCOPE_TEAM, "rank": r, "label": C.RANK_LABELS[r]} for r in C.TEAM_RANKS],
            "gifts": list(C.GIFT_SUGGESTIONS), "defaults": settings.DEFAULTS,
            "default_prizes": [dict(p) for p in C.DEFAULT_PRIZES],
            "limits": {"questions": C.MAX_QUESTIONS, "options": C.MAX_OPTIONS, "text": C.MAX_TEXT,
                       "option_text": C.MAX_OPTION_TEXT, "prizes": C.MAX_PRIZES,
                       "tickets_week": C.TICKETS_PER_WEEK}}


def list_quizzes(ctx, repo):
    require_host(ctx)
    rows = repo.list_quizzes()
    names = repo.full_names([r["owner"] for r in rows])
    for r in rows:
        r["owner_name"] = names.get(r["owner"], r["owner"])
    return {"quizzes": rows, "rooms": recent_rooms(repo)}


def recent_rooms(repo):
    rows = repo.recent_sessions()
    names = repo.full_names([r["host"] for r in rows])
    for r in rows:
        r["host_name"] = names.get(r["host"], r["host"])
        r["live"] = r["phase"] in C.LIVE_PHASES
    return rows


def get(ctx, repo, name):
    require_host(ctx)
    return {"quiz": _view(require_found(repo.get_quiz(name), "bộ quiz")), "meta": meta()}


def new(ctx, repo, template=None):
    require_host(ctx)
    tpl = TEMPLATES.get(template) or TEMPLATES["after_class"]
    return {"quiz": {"name": None, "title": "", "description": "", "status": C.QUIZ_DRAFT,
                     "template": template if template in TEMPLATES else "after_class", "modified": "",
                     "questions": [], "settings": settings.clean_settings(tpl["settings"]),
                     "prizes": [dict(p) for p in C.DEFAULT_PRIZES]}, "meta": meta()}


def save(ctx, repo, payload, rid=Q.default_rid):
    """Luu nhap thi CHO PHEP cau chua xong (tra ve loi tung cau de to do); danh dau "San sang"
    thi moi cau phai hop le. Khoa lac quan: `modified` lech -> co nguoi vua sua."""
    require_host(ctx)
    payload = payload if isinstance(payload, dict) else {}
    title = " ".join(str(payload.get("title") or "").split())[:140]
    if not title:
        raise FieldErrors("Bộ quiz cần tên.", {"title": "Đặt tên cho bộ quiz."})
    ready = payload.get("status") == C.QUIZ_READY
    if ready:
        qs, errs = Q.require_valid(payload.get("questions") or [], rid), {}
    else:
        qs, errs = Q.clean_questions(payload.get("questions") or [], rid)
    fields = {"title": title, "description": " ".join(str(payload.get("description") or "").split())[:500],
              "status": C.QUIZ_READY if ready else C.QUIZ_DRAFT,
              "template": payload.get("template") if payload.get("template") in TEMPLATES else "",
              "questions": qs, "settings": settings.clean_settings(payload.get("settings")),
              "prizes": prizes.clean_prizes(payload.get("prizes"))}
    name = payload.get("name")
    if name:
        cur = require_found(repo.get_quiz(name), "bộ quiz")
        if payload.get("modified") != cur["modified"]:
            raise QuizError("Bộ quiz vừa được người khác sửa. Tải lại trang để lấy bản mới.")
        repo.save_quiz(name, fields)
    else:
        name = repo.insert_quiz(fields)
    out = _view(repo.get_quiz(name))
    return {"quiz": out, "errors": errs}


def archive(ctx, repo, name):
    require_host(ctx)
    require_found(repo.get_quiz(name), "bộ quiz")
    repo.save_quiz(name, {"status": C.QUIZ_ARCHIVED})
    return {"name": name}


def import_file(ctx, repo, file_url):
    """Doc tep Excel (Kahoot / Wayground) -> cau hoi THO cho trinh soan (chua luu - nguoi soan
    xem lai roi bam Luu)."""
    require_host(ctx)
    if not file_url or not str(file_url).startswith(("/files/", "/private/files/")):
        raise QuizError("Chưa chọn tệp Excel.")
    if repo.file_owner(file_url) not in (ctx.user,) and not ctx.is_admin:
        raise QuizError("Chỉ nhập được tệp do chính bạn tải lên.")
    try:
        rows = repo.read_xlsx_rows(file_url)
    except QuizError:
        raise
    except Exception:
        raise QuizError("Không đọc được tệp - cần tệp .xlsx theo mẫu Kahoot hoặc Wayground.")
    raw = importer.parse(rows)
    _, errs = Q.clean_questions(raw)
    return {"questions": raw, "count": len(raw), "errors": errs}

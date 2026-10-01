# Copyright (c) 2026, eCentric and contributors
"""Doc mot khao sat (dict tu repository) thanh cac manh ma service tra cho trang.
Dung chung cho builder / respond / results - de ba noi khong tu dien giai form_json, trang
thai hay danh sach qua theo ba cach khac nhau."""
import copy
import json

from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.domain import lifecycle, schema

#: Cot cai dat nguoi soan sua duoc tu trang (khong gom status / dem / dau vet phat hanh).
SETTINGS_FIELDS = ("title", "description", "accent_color", "open_at", "close_at", "anonymous",
                   "allow_edit", "show_progress", "shuffle_questions", "show_summary",
                   "response_limit", "is_quiz", "show_score", "notify_on_publish",
                   "confirmation_message", "audience_mode", "reward_mode", "wheel_expected",
                   "reward_note")
CHECK_FIELDS = ("anonymous", "allow_edit", "show_progress", "shuffle_questions", "show_summary",
                "is_quiz", "show_score", "notify_on_publish")
INT_FIELDS = ("response_limit", "wheel_expected")
DATETIME_FIELDS = ("open_at", "close_at")
#: Mac dinh khi tao moi - ghi tuong minh thay vi dua vao default cua DocType JSON, de mau /
#: nhan ban / test cung ra mot ket qua.
DEFAULTS = {"accent_color": "#2C3DA6", "show_progress": 1, "show_score": 1, "notify_on_publish": 1,
            "audience_mode": C.AUDIENCE_ALL, "reward_mode": C.REWARD_NONE}


def dt(v):
    return str(v)[:19] if v else ""


def form_of(survey):
    raw = survey.get("form_json")
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    return schema.normalize(data)


def effective(repo, survey):
    return lifecycle.effective_status(
        survey.get("status"), repo.to_datetime(survey.get("open_at")),
        repo.to_datetime(survey.get("close_at")), repo.now(),
        int(survey.get("response_count") or 0), int(survey.get("response_limit") or 0))


def public_form(form):
    """Ban form gui cho NGUOI TRA LOI: bo dap an dung cua bai kiem tra."""
    out = copy.deepcopy(form)
    for it in out["items"]:
        it.pop("correct", None)
    return out


def prizes(survey):
    return [{"id": p.get("name"), "label": p.get("label") or "", "color": p.get("color") or "",
             "quantity": int(p.get("quantity") or 0), "awarded": int(p.get("awarded") or 0)}
            for p in survey.get("prizes") or []]


def settings(survey):
    out = {}
    for f in SETTINGS_FIELDS:
        v = survey.get(f)
        if f in DATETIME_FIELDS:
            v = dt(v)
        elif f in CHECK_FIELDS or f in INT_FIELDS:
            v = int(v or 0)
        out[f] = v if v is not None else ""
    return out


def card(repo, survey, extra=None):
    """Mot the khao sat cho cac danh sach (hub, quan ly)."""
    form = form_of(survey)
    d = {"name": survey.get("name"), "title": survey.get("title") or "",
         "description": survey.get("description") or "", "status": survey.get("status"),
         "effective": effective(repo, survey), "open_at": dt(survey.get("open_at")),
         "close_at": dt(survey.get("close_at")), "anonymous": int(survey.get("anonymous") or 0),
         "is_quiz": int(survey.get("is_quiz") or 0), "reward_mode": survey.get("reward_mode") or C.REWARD_NONE,
         "accent_color": survey.get("accent_color") or "", "responses": int(survey.get("response_count") or 0),
         "questions": len(schema.questions(form)), "modified": dt(survey.get("modified")),
         "owner": survey.get("owner") or ""}
    d.update(extra or {})
    return d

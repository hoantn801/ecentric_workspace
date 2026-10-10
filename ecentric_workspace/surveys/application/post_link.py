# Copyright (c) 2026, eCentric and contributors
"""Khao sat GAN VAO BAI Tin noi bo - API khai bao cua module Khao sat cho module internal_posts
(ben kia khong doc DocType nao cua khao sat).

    options(user, roles)            -> khao sat nguoi soan bai duoc gan (minh tao / cung quan ly,
                                       dang Nhap hoac con mo)
    can_attach(user, roles, name)   -> True / False
    card(user, roles, name)         -> the khao sat cho TRANG BAI theo nguoi xem, hoac None (an)
    badges(user, roles, names)      -> {ten khao sat: nhan} cho the bai o danh sach / trang chu

Trang thai the (PO duyet mockup 10/10/2026):
    todo    - dang mo, nguoi xem thuoc doi tuong, chua nop        -> nut "Lam khao sat"
    done    - da nop                                              -> "Xem / sua cau tra loi"
    soon    - da phat hanh, chua toi gio mo
    closed  - da dong (chi hien cho nguoi thuoc doi tuong / da nop)
    draft   - khao sat con Nhap: CHI nguoi quan ly khao sat thay (nhan vien khong thay gi)
Nguoi khong thuoc doi tuong -> None (khong hien the).
"""
import math

from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.application import access, view
from ecentric_workspace.surveys.domain import schema
from ecentric_workspace.surveys.infrastructure import repository as default_repo

#: Uoc thoi gian lam: ~3 cau / phut.
QUESTIONS_PER_MINUTE = 3


def _ctx(user, roles):
    return access.Ctx(user, roles)


def _date_label(v):
    return v.strftime("%d/%m/%Y") if v else ""


def options(user, roles, repo=default_repo):
    ctx = _ctx(user, roles)
    out = []
    for s in repo.surveys_managed_by(user, all_surveys=ctx.is_admin):
        eff = view.effective(repo, s)
        if eff == C.EFFECTIVE_CLOSED:
            continue
        out.append({"name": s["name"], "title": s.get("title") or s["name"],
                    "draft": eff == C.EFFECTIVE_DRAFT,
                    "label": "%s · %s%s" % (s["name"], s.get("title") or "",
                                            " (Nháp)" if eff == C.EFFECTIVE_DRAFT else "")})
    return out


def can_attach(user, roles, name, repo=default_repo):
    survey = repo.get_survey(name) if name else None
    return bool(survey) and access.can_manage(_ctx(user, roles), survey)


def _base(repo, survey):
    form = view.form_of(survey)
    n = len(schema.questions(form))
    close = repo.to_datetime(survey.get("close_at"))
    now = repo.now()
    days = (close.date() - now.date()).days if close else None
    return {"name": survey["name"], "title": survey.get("title") or "", "questions": n,
            "minutes": max(1, int(math.ceil(n / float(QUESTIONS_PER_MINUTE)))) if n else 0,
            "close_label": _date_label(close), "days_left": days if days is not None and days >= 0 else None,
            "anonymous": bool(survey.get("anonymous")), "url": C.fill_url(survey["name"]),
            "manage_url": "/%s?s=%s" % (C.ROUTE_BUILDER, survey["name"])}


def card(user, roles, name, repo=default_repo):
    survey = repo.get_survey(name) if name else None
    if not survey:
        return None
    ctx = _ctx(user, roles)
    manager = access.can_manage(ctx, survey)
    eff = view.effective(repo, survey)
    d = _base(repo, survey)
    d["is_manager"] = manager
    if eff == C.EFFECTIVE_DRAFT:
        return dict(d, state="draft") if manager else None
    eligible = access.eligible_set(repo, survey)
    part = repo.get_participant(survey["name"], user)
    if not part and user not in eligible:
        return None
    total = len(eligible)
    resp = int(survey.get("response_count") or 0)
    d["pct"] = min(100, int(round(resp * 100.0 / total))) if total else 0
    if part:
        at = repo.to_datetime(part.get("submitted_at"))
        d.update(submitted_label=at.strftime("%H:%M %d/%m") if at else "",
                 can_edit=bool(survey.get("allow_edit")) and not survey.get("anonymous")
                 and eff == C.EFFECTIVE_OPEN)
        if eff == C.EFFECTIVE_CLOSED:
            return dict(d, state="closed", done=True)
        return dict(d, state="done")
    if eff == C.EFFECTIVE_CLOSED:
        return dict(d, state="closed", done=False)
    if eff == C.EFFECTIVE_SCHEDULED:
        opens = repo.to_datetime(survey.get("open_at"))
        return dict(d, state="soon", open_label=opens.strftime("%H:%M %d/%m/%Y") if opens else "")
    return dict(d, state="todo")


def badges(user, roles, names, repo=default_repo):
    """Nhan tren the bai: chi khi khao sat dang mo VA nguoi xem thuoc doi tuong.
    -> {ten: {"kind": "todo"|"done", "label": "..."}}."""
    out, cache = {}, {}
    names = [n for n in dict.fromkeys(names or []) if n]
    if not names:
        return out
    mine = {p["survey"] for p in repo.participations_of(user)}
    for s in repo.surveys_by_names(names):
        if view.effective(repo, s) != C.EFFECTIVE_OPEN:
            continue
        if s["name"] in mine:
            out[s["name"]] = {"kind": "done", "label": "Đã làm khảo sát"}
            continue
        full = repo.get_survey(s["name"])
        if not access.is_eligible(repo, _ctx(user, roles), full, cache):
            continue
        close = repo.to_datetime(s.get("close_at"))
        days = (close.date() - repo.now().date()).days if close else None
        label = "Khảo sát · còn %d ngày" % days if days and days > 0 else (
            "Khảo sát · hạn hôm nay" if days == 0 else "Khảo sát")
        out[s["name"]] = {"kind": "todo", "label": label}
    return out

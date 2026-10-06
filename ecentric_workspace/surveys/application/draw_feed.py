# Copyright (c) 2026, eCentric and contributors
"""Du lieu quay so cho POPUP TRANG CHU "Hom nay o eCentric" - API khai bao cua module Khao sat
cho module home_today (khong DocType nao cua khao sat bi doc tu ben kia).

    for_user(user)  -> {"server_now", "draws", "upcoming", "timers"}
    any_soon()      -> co luot quay nao trong DRAW_TILE_DAYS ngay toi (ca cong ty, cache)

  * draws    : luot quay HOM NAY, tu T-5 phut toi het ngay: dem nguoc -> dang quay -> ket qua.
  * upcoming : "Luot quay tiep theo" (PO 01/10): cac luot sau, kem tinh trang cua chinh nguoi xem.
  * timers   : luot quay hom nay CHUA toi T-5 - popup hen gio tu mo dung luc (phong khi mat socket).

Chi tra luot quay ma nguoi xem nam trong doi tuong. Khong bao gio tra ke hoach vong quay hay
ket qua truoc gio.
"""
import datetime

from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.application import access, submit_reward, view
from ecentric_workspace.surveys.domain import rewards
from ecentric_workspace.surveys.infrastructure import repository as default_repo

SOON_CACHE_KEY = "ec_survey:draw_soon:v1"
SOON_TTL = 300


def _short(name):
    """Ten goi tren lan dua: tu cuoi cua ho ten Viet ("Tran Minh Anh" -> "Anh")."""
    parts = str(name or "").split()
    return parts[-1] if parts else ""


def any_soon(repo=default_repo):
    """Trang chu goi o MOI lan mo (Jinja) -> mot truy van dem, cache 5 phut cho ca cong ty."""
    hit = repo.cache_get(SOON_CACHE_KEY)
    if hit is not None:
        return bool(int(hit))
    now = repo.now()
    start = datetime.datetime.combine(now.date(), datetime.time.min)
    n = repo.count_draw_surveys(start, now + datetime.timedelta(days=C.DRAW_TILE_DAYS))
    repo.cache_set(SOON_CACHE_KEY, 1 if n else 0, SOON_TTL)
    return bool(n)


def invalidate(repo=default_repo):
    """Goi khi phat hanh / doi gio quay - de trang chu biet ngay, khong doi het cache 5 phut."""
    try:
        repo.cache_delete(SOON_CACHE_KEY)
    except Exception:
        pass


def _state(survey, at, now, drawn_at=None):
    if survey.get("draw_at"):
        # "Dang quay" tinh tu luc THUC SU chot (nguoi quan ly co the bam "Quay ngay" som hon gio hen).
        base = min(at, drawn_at) if drawn_at else at
        return C.DRAW_LIVE if now < base + datetime.timedelta(minutes=C.DRAW_LIVE_MIN) else C.DRAW_DONE
    return C.DRAW_COUNTDOWN if now < at else C.DRAW_LIVE        # qua gio ma job chua chay: popup cho


def _prizes(survey):
    return [{"rank": i, "label": p["label"], "quantity": p["quantity"]}
            for i, p in enumerate(view.prizes(survey), start=1) if p["quantity"] > 0]


def _results(repo, survey, user):
    data = view.draw_results(survey)
    if not data or not isinstance(data, dict):
        return [], [], 0
    if data.get("kind") == C.REWARD_NUMBER:
        items = data.get("items") or []
        names = repo.user_names([i["user"] for i in items if i.get("user")])
        res = [{"rank": i["rank"], "prize": i.get("label") or "",
                "number": rewards.format_number(i["number"], data.get("top")),
                "name": names.get(i["user"], i["user"]) if i.get("user") else "",
                "is_me": i.get("user") == user} for i in items]
        return res, [], data.get("holders") or 0
    order = data.get("order") or []
    winners = data.get("winners") or []
    lanes = set(range(min(len(winners), len(order))))
    if user in order:
        lanes.add(order.index(user))
    k = 0
    while len(lanes) < min(C.RACE_LANES, len(order)):
        lanes.add(k)
        k += 1
    picked = sorted(lanes)
    names = repo.user_names([order[i] for i in picked] + [w["user"] for w in winners])
    # Khao sat AN DANH: chi lo ten nguoi ve dau (nhan qua) - cac xe khac khong ghi ten.
    named = {w["user"] for w in winners} | {user}
    show = lambda u: names.get(u, u) if (u in named or not survey.get("anonymous")) else ""
    racers = [{"place": i + 1, "name": show(order[i]), "short": _short(show(order[i])),
               "is_me": order[i] == user} for i in picked]
    res = [{"rank": w["rank"], "place": w["place"], "prize": w.get("label") or "",
            "name": names.get(w["user"], w["user"]), "is_me": w["user"] == user} for w in winners]
    return res, racers, len(order)


def _draw_item(repo, survey, part, user, now):
    at = repo.to_datetime(survey.get("draw_scheduled_at"))
    top = view.number_top(survey)
    item = {"name": survey["name"], "title": survey.get("title") or "", "mode": survey.get("reward_mode"),
            "accent": survey.get("accent_color") or "", "draw_at": view.dt(at),
            "state": _state(survey, at, now, repo.to_datetime(survey.get("draw_at"))),
            "range": [1, top], "prizes": _prizes(survey), "url": C.fill_url(survey["name"]),
            "joined": bool(part), "my_number": "", "holders": 0, "racers": [], "results": [],
            "drawn": bool(survey.get("draw_at")),
            "racer_total": 0, "note": survey.get("reward_note") or ""}
    if survey.get("reward_mode") == C.REWARD_NUMBER:
        held = submit_reward.holders(repo, survey["name"])
        item["holders"] = len(held)
        mine = [n for n, u in held.items() if u == user]
        item["my_number"] = rewards.format_number(mine[0], top) if mine else ""
    else:
        item["racer_total"] = repo.count_participants(survey["name"])
    if survey.get("draw_at"):
        item["results"], item["racers"], total = _results(repo, survey, user)
        if item["mode"] == C.REWARD_RACE:
            item["racer_total"] = total
    return item


def _upcoming_item(repo, survey, part, now):
    at = repo.to_datetime(survey.get("draw_scheduled_at"))
    eff = view.effective(repo, survey)
    top = view.number_top(survey)
    if part and survey.get("reward_mode") == C.REWARD_NUMBER:
        n = int(part.get("lucky_number") or 0)
        me, num = ("holding", rewards.format_number(n, top)) if n else ("pick", "")
    elif part:
        me, num = "joined", ""
    elif eff == C.EFFECTIVE_SCHEDULED:
        me, num = "not_open", ""
    elif eff == C.EFFECTIVE_OPEN:
        me, num = "not_submitted", ""
    else:
        me, num = "closed", ""
    return {"name": survey["name"], "title": survey.get("title") or "", "mode": survey.get("reward_mode"),
            "draw_at": view.dt(at), "days_left": (at.date() - now.date()).days, "me": me, "my_number": num,
            "open_at": view.dt(survey.get("open_at")), "url": C.fill_url(survey["name"]),
            "prizes": _prizes(survey), "note": survey.get("reward_note") or ""}     # hop qua dau dong (PO 02/10)


def one(user, name, repo=default_repo):
    """MOT luot quay - popup hoi lien tuc luc "dang chot ket qua" (moi 5 giay / nguoi).
    Chua chot -> tra ngay ban toi gian, KHONG tinh doi tuong (duong nong, review 01/10).
    Da chot -> kiem doi tuong roi tra du ket qua."""
    survey = repo.get_survey(name)
    if not survey or survey.get("reward_mode") not in C.SCHEDULED_MODES or survey.get("status") == C.STATUS_DRAFT:
        return None
    if not survey.get("draw_at"):
        return {"name": name, "drawn": False, "results": []}
    if user not in access.eligible_set(repo, survey):
        return None
    part = repo.get_participant(name, user)
    return _draw_item(repo, survey, part, user, repo.now())


def for_user(user, repo=default_repo):
    now = repo.now()
    out = {"server_now": view.dt(now), "draws": [], "upcoming": [], "timers": []}
    if not user or user == "Guest":
        return out
    start = datetime.datetime.combine(now.date(), datetime.time.min)
    rows = repo.draw_surveys(start, now + datetime.timedelta(days=C.DRAW_UPCOMING_DAYS))
    if not rows:
        return out
    mine = {p["survey"]: p for p in repo.participations_of(user)}
    cache = {}
    lead = datetime.timedelta(minutes=C.DRAW_NOTIFY_BEFORE_MIN)
    for row in rows:
        at = repo.to_datetime(row.get("draw_scheduled_at"))
        drawn_at = repo.to_datetime(row.get("draw_at"))
        if not drawn_at and at < start:
            continue
        # Da quay (ke ca quay tay som hon gio hen): chi hien ket qua trong NGAY quay, khong con la "sap toi".
        if drawn_at and drawn_at.date() != now.date() and at.date() != now.date():
            continue
        survey = repo.get_survey(row["name"])
        if not survey or user not in access.eligible_set(repo, survey, cache):
            continue
        part = mine.get(survey["name"])
        if drawn_at or (at.date() == now.date() and now >= at - lead):
            out["draws"].append(_draw_item(repo, survey, part, user, now))
        elif at > now:
            if at.date() == now.date():
                out["timers"].append({"name": survey["name"], "open_at": view.dt(at - lead), "draw_at": view.dt(at)})
            if len(out["upcoming"]) < C.DRAW_UPCOMING_MAX:
                out["upcoming"].append(_upcoming_item(repo, survey, part, now))
    return out

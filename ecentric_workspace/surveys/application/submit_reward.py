# Copyright (c) 2026, eCentric and contributors
"""Phan thuong gan voi MOT nguoi tham gia: cap so may man luc nop, quay vong quay, va trang
thai qua de trang ve lai (mo lai trang van thay dung ket qua, khong quay lai duoc).

Khac biet voi /khao-sat tra sua 07/2026: o day KHONG co cach nao quay ma chua nop - luot
quay doc dong EC Survey Participant cua chinh nguoi goi (chi sinh ra khi nop thanh cong).
"""
import random

from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.application import access, view
from ecentric_workspace.surveys.domain import rewards
from ecentric_workspace.surveys.domain.errors import SurveyError

_RNG = random.SystemRandom()


def state(survey, part):
    mode = survey.get("reward_mode") or C.REWARD_NONE
    if mode == C.REWARD_NONE or not part:
        return {"mode": mode}
    n = int(part.get("lucky_number") or 0)
    return {"mode": mode, "note": survey.get("reward_note") or "",
            "lucky_number": rewards.format_number(n) if n else "",
            "result": part.get("reward_result") or "", "prize": part.get("prize") or "",
            "prize_label": part.get("prize_label") or "",
            "can_spin": mode == C.REWARD_WHEEL and not part.get("reward_result")}


def on_submit(repo, survey, pname, now):
    """Goi NGAY sau khi chen nguoi tham gia, trong luc dang giu khoa khao sat."""
    part = {"name": pname, "reward_result": "", "lucky_number": 0}
    if survey.get("reward_mode") == C.REWARD_NUMBER:
        cur = repo.get_survey(survey["name"])            # doc lai sau khoa: bo dem moi nhat
        n = int(cur.get("lucky_seq") or 0) + 1
        repo.set_survey_values(survey["name"], {"lucky_seq": n})
        repo.update_participant(pname, {"lucky_number": n})
        part["lucky_number"] = n
    return part


def spin(ctx, name, repo, rng=None):
    rng = rng or _RNG
    survey = repo.get_survey(name)
    if not survey or survey.get("reward_mode") != C.REWARD_WHEEL:
        raise SurveyError("Khảo sát này không có vòng quay.")
    if not repo.get_participant(name, ctx.user):
        raise SurveyError("Nộp khảo sát xong mới được quay.")
    repo.lock_survey(name)
    survey = repo.get_survey(name)                       # sau khoa: so qua da trao moi nhat
    part = repo.get_participant(name, ctx.user)
    if part.get("reward_result"):
        raise SurveyError("Bạn đã quay rồi.")
    prizes = view.prizes(survey)
    expected = int(survey.get("wheel_expected") or 0) or len(access.eligible_set(repo, survey))
    won, prize, _p = rewards.spin(prizes, expected, repo.count_spins(name), rng)
    now = repo.now()
    values = {"reward_result": C.RESULT_WIN if won else C.RESULT_LOSE, "rewarded_at": now}
    if won:
        repo.set_prize_awarded(prize["id"], prize["awarded"] + 1)
        values.update({"prize": prize["id"], "prize_label": prize["label"]})
    repo.update_participant(part["name"], values)
    part.update(values)
    return state(survey, part)


def draw(ctx, name, repo, rng=None):
    """Quay so may man: rut nguoi trung cho moi hang qua CON LAI. Bam lai duoc khi them qua."""
    rng = rng or _RNG
    survey = repo.get_survey(name)
    access.require_manage(ctx, survey)
    if survey.get("reward_mode") != C.REWARD_NUMBER:
        raise SurveyError("Khảo sát này không dùng con số may mắn.")
    repo.lock_survey(name)
    survey = repo.get_survey(name)
    parts = repo.participants(name)
    candidates = [p["user"] for p in parts if p.get("lucky_number") and p.get("reward_result") != C.RESULT_WIN]
    prizes = view.prizes(survey)
    if not candidates:
        raise SurveyError("Chưa có ai nhận số may mắn để quay.")
    if rewards.remaining(prizes) <= 0:
        raise SurveyError("Đã trao hết quà.")
    result = rewards.draw(prizes, candidates, rng)
    by_user = {p["user"]: p for p in parts}
    now, out = repo.now(), []
    for p in prizes:
        won = result.get(p["id"]) or []
        if won:
            repo.set_prize_awarded(p["id"], p["awarded"] + len(won))
        for u in won:
            repo.update_participant(by_user[u]["name"], {
                "reward_result": C.RESULT_WIN, "prize": p["id"], "prize_label": p["label"],
                "rewarded_at": now})
            out.append({"user": u, "prize": p["label"],
                        "lucky_number": rewards.format_number(by_user[u]["lucky_number"])})
            repo.notify(u, "Chúc mừng! Bạn trúng %s" % p["label"],
                        "Số may mắn %s của bạn trong khảo sát “%s” đã trúng. %s" % (
                            rewards.format_number(by_user[u]["lucky_number"]), survey.get("title"),
                            survey.get("reward_note") or ""),
                        C.fill_url(name), name, "survey|win|%s|%s" % (name, u))
    repo.set_survey_values(name, {"draw_at": now})
    names = repo.user_names([w["user"] for w in out])
    for w in out:
        w["name"] = names.get(w["user"], w["user"])
    return {"winners": out}

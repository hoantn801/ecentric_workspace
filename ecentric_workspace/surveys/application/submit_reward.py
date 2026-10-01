# Copyright (c) 2026, eCentric and contributors
"""Phan thuong gan voi MOT nguoi tham gia: vong quay chia dot, chon so may man, trang thai
qua de trang ve lai (mo lai trang van thay dung ket qua, khong quay lai duoc).

Khong co cach nao quay / chon so ma chua nop - moi duong doc dong EC Survey Participant cua
chinh nguoi goi (chi sinh ra khi nop thanh cong). Quay theo gio hen (so may man, dua ve dich)
nam o draw_service.py.
"""
import json
import random

from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.application import access, view
from ecentric_workspace.surveys.domain import rewards
from ecentric_workspace.surveys.domain.errors import SurveyError

_RNG = random.SystemRandom()


def expected_spins(repo, survey):
    return int(survey.get("wheel_expected") or 0) or len(access.eligible_set(repo, survey))


def make_plan(repo, survey, rng=None):
    """Giau qua cho cac luot CON LAI va luu (bi mat). Goi luc phat hanh, khi doi qua giua
    chung, va o luot quay dau tien neu khao sat cu chua co ke hoach."""
    slots = rewards.plan(view.prizes(survey), expected_spins(repo, survey),
                         repo.count_spins(survey["name"]), rng or _RNG)
    repo.set_survey_values(survey["name"], {"wheel_plan": json.dumps(slots)})
    return slots


def holders(repo, name):
    """{so: user} cua nguoi dang giu so."""
    return {int(p["lucky_number"]): p["user"] for p in repo.participants(name) if p.get("lucky_number")}


def number_board(repo, survey, me):
    """Bang so CONG KHAI (PO: "cong khai so mng chon luon cho vui"). Khao sat AN DANH: chi hien
    so da co nguoi giu, khong hien ten (ten = lo ai da nop phieu an danh)."""
    held = holders(repo, survey["name"])
    anon = bool(survey.get("anonymous"))
    names = {} if anon else repo.user_names(list(held.values()))
    top = view.number_top(survey)
    return {"top": top, "count": len(held),
            "holders": [{"n": n, "label": rewards.format_number(n, top),
                         "name": "" if anon else names.get(u, u), "me": u == me}
                        for n, u in sorted(held.items())]}


def _pick_open(repo, survey):
    if survey.get("draw_at"):
        return False
    at = repo.to_datetime(survey.get("draw_scheduled_at"))
    return not at or repo.now() < at


def state(repo, survey, part, me=None):
    mode = survey.get("reward_mode") or C.REWARD_NONE
    if mode == C.REWARD_NONE or not part:
        return {"mode": mode}
    top = view.number_top(survey)
    n = int(part.get("lucky_number") or 0)
    out = {"mode": mode, "note": survey.get("reward_note") or "",
           "result": part.get("reward_result") or "", "prize": part.get("prize") or "",
           "prize_label": part.get("prize_label") or "",
           "draw_at": view.dt(survey.get("draw_scheduled_at")), "drawn": bool(survey.get("draw_at"))}
    if mode == C.REWARD_WHEEL:
        # CHI hien luot / dot SAU khi da quay. Truoc khi quay ma biet "minh la luot thu X, dot nay
        # con qua / da het" thi nguoi choi canh duoc luc quay (review 01/10) - mat tinh cong bang.
        seq = int(part.get("spin_seq") or 0)
        out.update({"can_spin": not part.get("reward_result"),
                    "waves": rewards.wave_info(view.wheel_plan(survey), seq, view.prizes(survey), spun=True)
                    if seq else None})
    elif mode == C.REWARD_NUMBER:
        out.update({"lucky_number": rewards.format_number(n, top) if n else "", "number": n,
                    "can_pick": _pick_open(repo, survey), "board": number_board(repo, survey, me or part.get("user"))})
    return out


def on_submit(repo, survey, pname, now):
    """Goi NGAY sau khi chen nguoi tham gia, trong luc dang giu khoa khao sat. Khong cap gi
    them: so may man do nguoi dung tu chon, xe dua thi ai nop cung co."""
    return {"name": pname, "reward_result": "", "lucky_number": 0}


def spin(ctx, name, repo, rng=None):
    rng = rng or _RNG
    survey = repo.get_survey(name)
    if not survey or survey.get("reward_mode") != C.REWARD_WHEEL:
        raise SurveyError("Khảo sát này không có vòng quay.")
    if not repo.get_participant(name, ctx.user):
        raise SurveyError("Nộp khảo sát xong mới được quay.")
    repo.lock_survey(name)
    survey = repo.get_survey(name)                       # sau khoa: so qua / luot moi nhat
    part = repo.get_participant(name, ctx.user)
    if part.get("reward_result"):
        raise SurveyError("Bạn đã quay rồi.")
    slots = view.wheel_plan(survey)
    if not slots and survey.get("wheel_plan") in (None, ""):
        slots = make_plan(repo, survey, rng)             # khao sat phat hanh truoc ban chia dot
    seq = repo.count_spins(name) + 1
    prizes = view.prizes(survey)
    pid = rewards.spin_result(slots, seq, prizes)
    prize = next((p for p in prizes if p["id"] == pid), None)
    values = {"reward_result": C.RESULT_WIN if prize else C.RESULT_LOSE,
              "rewarded_at": repo.now(), "spin_seq": seq}
    if prize:
        repo.set_prize_awarded(prize["id"], prize["awarded"] + 1)
        values.update({"prize": prize["id"], "prize_label": prize["label"]})
    repo.update_participant(part["name"], values)
    part.update(values)
    return state(repo, survey, part, ctx.user)


def pick_number(ctx, name, number, repo, rng=None):
    """Chon / doi so may man. number = 0 -> may chon giup mot so con trong."""
    rng = rng or _RNG
    survey = repo.get_survey(name)
    if not survey or survey.get("reward_mode") != C.REWARD_NUMBER:
        raise SurveyError("Khảo sát này không dùng số may mắn.")
    if not repo.get_participant(name, ctx.user):
        raise SurveyError("Nộp khảo sát xong mới chọn được số.")
    try:
        number = int(number or 0)
    except (TypeError, ValueError):
        raise SurveyError("Số không hợp lệ.")
    repo.lock_survey(name)                               # hai nguoi cung bam mot so: nguoi sau doi
    survey = repo.get_survey(name)
    if not _pick_open(repo, survey):
        raise SurveyError("Đã tới giờ quay - không chọn / đổi số được nữa.")
    top = view.number_top(survey)
    held = holders(repo, name)
    mine = [n for n, u in held.items() if u == ctx.user]
    taken = {n for n, u in held.items() if u != ctx.user}
    if not number:
        number = rewards.free_number(top, taken, rng)
        if not number:
            raise SurveyError("Đã hết số trống.")
    if not 1 <= number <= top:
        raise SurveyError("Chọn số trong khoảng 1 - %d." % top)
    if number in taken:
        raise SurveyError("Số %s vừa có người chọn. Chọn số khác nhé." % rewards.format_number(number, top))
    part = repo.get_participant(name, ctx.user)
    repo.update_participant(part["name"], {"lucky_number": number})
    repo.set_survey_values(name, {"lucky_seq": len(held) + (0 if mine else 1)})
    part["lucky_number"] = number
    return state(repo, survey, part, ctx.user)


def board(ctx, name, repo):
    """Bang so cho trang chon so (lam moi dinh ky) - nguoi trong doi tuong hoac da nop."""
    survey = repo.get_survey(name)
    if not survey or survey.get("reward_mode") != C.REWARD_NUMBER or survey.get("status") == C.STATUS_DRAFT:
        raise SurveyError("Khảo sát này không dùng số may mắn.")
    if not repo.get_participant(name, ctx.user) and not access.can_manage(ctx, survey) \
            and not access.is_eligible(repo, ctx, survey):
        raise SurveyError("Khảo sát này không dành cho bạn.")
    out = number_board(repo, survey, ctx.user)
    out["can_pick"] = _pick_open(repo, survey)
    return out

# Copyright (c) 2026, eCentric and contributors
"""Quay THEO GIO HEN: so may man va dua ve dich (PO Hoan chot 01/10/2026).

Lich mot dot quay, vi du hen 10:00 thu Ba:
  * 09:55 - bao chuong ERP + web push cho TOAN BO doi tuong khao sat, kem su kien realtime
    `ec_survey_draw` de popup trang chu dang mo tu bat (khong can tai lai trang).
  * 10:00 - job moi phut chot ket qua o SERVER (khoa dong khao sat, chay lai khong doi ket
    qua). Popup chi phat lai hieu ung dung ket qua do - ai mo trang muon van thay y het.
  * Ca ngay - popup giu ket qua (draw_feed.py); nguoi trung nhan thong bao rieng.

`tick` duoc goi moi phut tu hooks.py (scheduler_events cron */1). Mot truy van co chi muc tren
draw_scheduled_at, gan nhu luon rong; loi o mot khao sat khong lam ket cac khao sat khac.
Tat khan cap: site_config `ec_survey_draw_disabled: 1`.
"""
import datetime
import json
import random

from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.application import access, submit_reward, view
from ecentric_workspace.surveys.domain import rewards
from ecentric_workspace.surveys.domain.errors import SurveyError
from ecentric_workspace.surveys.infrastructure import repository as default_repo

_RNG = random.SystemRandom()
NOTIFY_JOB = "ecentric_workspace.surveys.application.draw_service.notify_soon"
KILL_SWITCH = "ec_survey_draw_disabled"
HOME_URL = "/"


def _labels(survey):
    return {p["id"]: p["label"] for p in view.prizes(survey)}


def run_draw(name, repo=default_repo, rng=None):
    """Chot ket qua MOT lan. Da quay roi -> tra None, khong lam gi (job / nut bam chay lai an toan)."""
    rng = rng or _RNG
    repo.lock_survey(name)
    survey = repo.get_survey(name)
    if not survey or survey.get("reward_mode") not in C.SCHEDULED_MODES or survey.get("draw_at"):
        return None
    if survey.get("status") == C.STATUS_DRAFT:
        raise SurveyError("Khảo sát chưa phát hành.")
    prizes, labels, parts = view.prizes(survey), _labels(survey), repo.participants(name)
    by_user = {p["user"]: p for p in parts}
    if survey["reward_mode"] == C.REWARD_NUMBER:
        top = view.number_top(survey)
        held = submit_reward.holders(repo, name)
        # Nop phieu ma chua chon so -> may boc giup mot so con trong roi moi quay (PO 02/10).
        auto = rewards.assign_missing(top, held, list(by_user), rng)
        for n, u in auto.items():
            repo.update_participant(by_user[u]["name"], {"lucky_number": n})
            by_user[u]["lucky_number"] = n
        held = {**held, **auto}
        items = rewards.lucky_draw(prizes, held, top, rng)
        for it in items:
            it["label"] = labels.get(it["prize"], "")
        data = {"kind": C.REWARD_NUMBER, "top": top, "holders": len(held), "items": items, "auto": len(auto)}
        winners = [it for it in items if it["user"]]
        losers = [u for u in held.values()]
    else:
        res = rewards.race(prizes, list(by_user), rng)
        for w in res["winners"]:
            w["label"] = labels.get(w["prize"], "")
        data = {"kind": C.REWARD_RACE, "order": res["order"], "winners": res["winners"]}
        winners, losers = res["winners"], res["order"]
    auto_users = set(auto.values()) if survey["reward_mode"] == C.REWARD_NUMBER else set()
    now = repo.now()
    won = {w["user"]: w for w in winners}
    count = {}
    for u in set(losers) | set(won):
        p = by_user.get(u)
        if not p:
            continue
        if u in won:
            w = won[u]
            count[w["prize"]] = count.get(w["prize"], 0) + 1
            repo.update_participant(p["name"], {"reward_result": C.RESULT_WIN, "prize": w["prize"],
                                                "prize_label": w["label"], "rewarded_at": now})
        else:
            repo.update_participant(p["name"], {"reward_result": C.RESULT_LOSE, "rewarded_at": now})
    for p in prizes:
        if count.get(p["id"]):
            repo.set_prize_awarded(p["id"], p["awarded"] + count[p["id"]])
    repo.set_survey_values(name, {"draw_results": json.dumps(data, ensure_ascii=False), "draw_at": now})
    for w in winners:
        how = ("Số may mắn %s%s của bạn đã trúng" % (rewards.format_number(w["number"], data["top"]),
                                                       " (máy bốc giúp)" if w["user"] in auto_users else "")
               if data["kind"] == C.REWARD_NUMBER else "Xe của bạn về thứ %d" % w["place"])
        try:
            repo.notify(w["user"], "Chúc mừng! Bạn trúng %s" % w["label"],
                        "%s trong “%s”. %s" % (how, survey.get("title"), survey.get("reward_note") or ""),
                        C.fill_url(name), name, "survey|win|%s|%s" % (name, w["user"]))
        except Exception:
            repo.log_error("survey win notify %s" % name)
    return data


def draw_now(ctx, name, repo=default_repo):
    """Nut "Quay ngay" cua nguoi quan ly (vi du lich bi hoan, can quay tay)."""
    survey = repo.get_survey(name)
    access.require_manage(ctx, survey)
    if survey.get("reward_mode") not in C.SCHEDULED_MODES:
        raise SurveyError("Khảo sát này không có quay số / đua về đích.")
    if survey.get("draw_at"):
        raise SurveyError("Đã quay xong rồi.")
    run_draw(name, repo)
    return {"drawn": True}


def tick(repo=default_repo):
    """Job moi phut: bao truoc 5 phut + chot ket qua dung gio."""
    if repo.site_flag(KILL_SWITCH):
        return {"skipped": True}
    now = repo.now()
    soon = now + datetime.timedelta(minutes=C.DRAW_NOTIFY_BEFORE_MIN)
    done = {"notified": 0, "drawn": 0}
    for s in repo.pending_draws(soon):
        name = s["name"]
        try:
            at = repo.to_datetime(s.get("draw_scheduled_at"))
            if not s.get("draw_notified_at"):
                repo.lock_survey(name)                     # hai tick chong nhau: chi mot tick bao
                if repo.get_survey(name).get("draw_notified_at"):
                    repo.commit()
                    continue
                late = now > at + datetime.timedelta(minutes=C.DRAW_NOTIFY_LATE_MIN)
                repo.set_survey_values(name, {"draw_notified_at": now})
                if not late:
                    repo.enqueue(NOTIFY_JOB, name=name)
                    done["notified"] += 1
                repo.commit()
            if now >= at and run_draw(name, repo) is not None:
                repo.commit()
                done["drawn"] += 1
        except Exception:
            repo.rollback()
            repo.log_error("survey draw tick %s" % name)
    return done


def notify_soon(name, repo=default_repo):
    """Job nen luc T-5: bao + day realtime cho tung nguoi trong doi tuong."""
    survey = repo.get_survey(name)
    if not survey or survey.get("draw_at"):
        return {"sent": 0}
    at = view.dt(survey.get("draw_scheduled_at"))[11:16]
    race = survey.get("reward_mode") == C.REWARD_RACE
    title = ("Còn %d phút nữa đua về đích: %s" if race else "Còn %d phút nữa quay số: %s") % (
        C.DRAW_NOTIFY_BEFORE_MIN, survey.get("title"))
    held = {} if race else {u: n for n, u in submit_reward.holders(repo, name).items()}
    joined = {p["user"] for p in repo.participants(name)}
    top = view.number_top(survey)
    sent = 0
    for u in sorted(access.eligible_set(repo, survey)):
        if race:
            mine = "Xe của bạn đã vào vạch xuất phát." if u in joined else "Bạn chưa nộp phiếu nên chưa có xe."
        else:
            if u in held:
                mine = "Số của bạn: %s." % rewards.format_number(held[u], top)
            elif u in joined:
                mine = "Bạn chưa chọn số - tới giờ máy sẽ bốc giúp bạn một số."
            else:
                mine = "Bạn chưa nộp phiếu nên chưa có số."
        try:
            # Gio hen nam trong khoa chong trung: doi gio quay thi dot bao moi khong bi nuot.
            repo.notify(u, title, "Mở trang chủ lúc %s để xem trực tiếp. %s" % (at, mine), HOME_URL, name,
                        "survey|draw_soon|%s|%s|%s" % (name, view.dt(survey.get("draw_scheduled_at")), u))
            repo.publish_realtime(u, C.REALTIME_DRAW, {"name": name})
            sent += 1
        except Exception:
            repo.log_error("survey draw notify %s %s" % (name, u))
    return {"sent": sent}

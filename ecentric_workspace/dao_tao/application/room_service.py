# Copyright (c) 2026, eCentric and contributors
"""Phong quiz phia NGUOI DAN: mo phong, chuyen pha, khoa cau + cong diem, ve dich + chia giai.

Moi thao tac doi pha chay DUOI KHOA dong phong (`repo.lock_session` = SELECT ... FOR UPDATE, tra
ban moi nhat) - hai nguoi dan bam cung luc, hay het gio dung luc nguoi dan bam "Khoa", chi MOT
thao tac thang; thao tac kia gap pha moi va bao loi nhe (hoac bo qua neu da dung pha).
"""
import random
import secrets

from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.application import ticket_service, views
from ecentric_workspace.dao_tao.application.access import require_found, require_host
from ecentric_workspace.dao_tao.domain import board, powers as PW, prizes, questions as Q, room, scoring, settings as S
from ecentric_workspace.dao_tao.domain.errors import QuizError


def open_room(ctx, repo, quiz_name, rng=None):
    require_host(ctx)
    quiz = require_found(repo.get_quiz(quiz_name), "bộ quiz")
    if quiz["status"] == C.QUIZ_ARCHIVED:
        raise QuizError("Bộ quiz này đã lưu trữ.")
    qs = Q.require_valid(quiz["questions"])          # chot lai (id moi) - sua bo quiz sau khong anh huong
    st = S.clean_settings(quiz["settings"])
    if S.strict(st):
        qs = [qs[i] for i in Q.perm("%s|%s" % (quiz_name, repo.now_ms()), len(qs))]
    rng = rng or random.SystemRandom()
    code = room.make_code(rng, repo.live_codes())
    name = repo.insert_session({"quiz": quiz_name, "title": quiz["title"], "code": code, "host": ctx.user,
                                "phase": C.PHASE_LOBBY, "q_index": 0, "version": 1,
                                "opened_ms": "0", "deadline_ms": "0", "questions": qs, "settings": st,
                                "prizes": prizes.clean_prizes(quiz["prizes"]),
                                # muoi cho hat giong xao - CHI nam o state_json, khong gui xuong may
                                "state": {"player_count": 0, "salt": secrets.token_hex(16)}})
    repo.touch_quiz_played(quiz_name)
    return {"session": name, "code": code}


def _host_session(ctx, repo, name):
    require_host(ctx)
    return require_found(repo.get_session(name), "phòng")


def host_state(ctx, repo, name):
    s = _host_session(ctx, repo, name)
    s = auto_lock(repo, s)
    players = repo.players(s["name"])
    # Ca luc da khoa / cong bo van hien "x/y da tra loi" (truoc day ve 0 ngay khi khoa - de hieu nham).
    answered = (repo.count_active_answers(s["name"], s["index"], locking=False)
                if s["phase"] in (C.PHASE_QUESTION, C.PHASE_LOCKED, C.PHASE_REVEAL) else 0)
    return views.host_view(s, players, answered, repo.now_ms())


def act(ctx, repo, name, action, expect_version=None):
    """Nut cua nguoi dan. expect_version: phien ban trang ma nguoi dan dang nhin - lech (nguoi
    khac / dong ho vua doi pha) thi KHONG lam, tra trang thai moi de bam lai cho dung."""
    require_host(ctx)
    s = require_found(repo.lock_session(name), "phòng")
    if expect_version not in (None, "", 0, "0") and int(expect_version) != s["version"]:
        return {"stale": True, "state": host_state(ctx, repo, name)}
    total = len(s["questions"])
    if action == C.ACT_END and s["phase"] == C.PHASE_QUESTION:
        s = _lock_question(repo, s)                  # ket thuc som giua cau: chot cau dang do truoc
    elif action == C.ACT_REVEAL and s["phase"] == C.PHASE_QUESTION:
        s = _lock_question(repo, s)                  # "Cong bo" khi chua khoa = khoa + cong bo
    phase, index = room.transition(action, s["phase"], s["index"], total,
                                   players=repo.count_players(s["name"]))
    now = repo.now_ms()
    vals = {"phase": phase, "index": index}
    if action in (C.ACT_START, C.ACT_NEXT):
        vals["opened_ms"] = now
        vals["deadline_ms"] = room.deadline_ms(now, s["questions"][index]["time"])
        vals["state"] = dict(s["state"], tally={})
        if action == C.ACT_START:
            vals["started_at"] = repo.now()
    if action == C.ACT_LOCK:
        _lock_question(repo, s)
        return {"state": host_state(ctx, repo, name)}
    if action == C.ACT_REVEAL:
        q = s["questions"][s["index"]]
        vals["state"] = dict(s["state"], tally=Q.tally(q, [a["answer"] for a in repo.answers(s["name"], s["index"])]))
    if action == C.ACT_END:
        vals["results"] = _finalize(repo, s)
        vals["ended_at"] = repo.now()
    if action == C.ACT_CANCEL:
        vals["ended_at"] = repo.now()
    v = repo.update_session(s["name"], vals)
    repo.publish_room(s["name"], v)
    return {"state": host_state(ctx, repo, name)}


def auto_lock(repo, s):
    """Het gio (+ GRACE) ma con o pha question -> khoa. Goi tu moi duong doc (nguoi dan / nguoi
    choi): khong can job theo phut, phong co nguoi la co request."""
    if s["phase"] != C.PHASE_QUESTION or repo.now_ms() <= s["deadline_ms"] + C.GRACE_MS:
        return s
    fresh = repo.lock_session(s["name"])
    if fresh and fresh["phase"] == C.PHASE_QUESTION and fresh["index"] == s["index"]:
        return _reveal(repo, _lock_question(repo, fresh))      # het gio -> cong bo luon (Hoan 13/11)
    return fresh or s                                # ban doc co khoa = moi nhat; KHONG nap lai Redis


def lock_if_all_answered(repo, s):
    """Goi sau khi chen cau tra loi (da giu khoa phong): ai cung tra loi roi thi khoa luon."""
    if s["phase"] != C.PHASE_QUESTION:
        return s
    # Chi dem cau tra loi cua nguoi CON trong phong (nguoi bi moi ra ma da tra loi khong tinh).
    if repo.count_active_answers(s["name"], s["index"]) >= max(1, repo.count_players(s["name"])):
        return _reveal(repo, _lock_question(repo, s))          # ai cung tra loi -> cong bo luon
    return s


def _reveal(repo, s):
    """PHAI dang giu khoa phong, cau da khoa: cong bo dap an + dem tung lua chon. Nguoi dan chi
    con bam Bang xep hang / Cau tiep (Hoan 13/11: het gio tu cong bo)."""
    q = s["questions"][s["index"]]
    # Doc CO KHOA: request nay co the da chup snapshot truoc khi cho khoa phong -> thieu cau tra loi.
    state = dict(s["state"], tally=Q.tally(q, [a["answer"] for a in repo.answers(s["name"], s["index"], locking=True)]))
    v = repo.update_session(s["name"], {"phase": C.PHASE_REVEAL, "state": state})
    repo.publish_room(s["name"], v)
    return dict(s, phase=C.PHASE_REVEAL, state=state, version=v)


def _lock_question(repo, s):
    """PHAI dang giu khoa phong. Cong diem cau hien tai cho moi nguoi, mat chuoi neu bo cau,
    gan co tra loi nhanh, chup bang xep hang vao state. -> phien ban phong moi (pha locked)."""
    idx = s["index"]
    q = s["questions"][idx]
    scored = q["type"] not in C.UNSCORED_TYPES
    ans = {a["user"]: a for a in repo.answers(s["name"], idx, locking=True) if not a.get("applied")}
    plist = repo.players(s["name"], locking=True)
    fast = dict(s["state"].get("fast") or {})
    pw_on = PW.enabled(s["settings"])
    thieves = []
    for p in plist:
        if p.get("kicked"):
            continue
        a = ans.get(p["user"])
        upd = {}
        pw, pw_ids = None, []
        if pw_on:
            try:
                pw = PW.clean_state(p.get("powers"))
                pw_ids = PW.effective(pw, idx)
                if scored and "steal" in pw_ids:
                    thieves.append(p["user"])
            except Exception:
                repo.log_error("dao_tao power lock %s %s" % (s["name"], p["user"]))
                pw, pw_ids = None, []
        if a:
            upd["score"] = max(0, p["score"] + int(a["points"] or 0))   # "Lieu an nhieu" sai co the am
            upd["answered"] = p["answered"] + 1
            if scored:
                upd["streak"] = int(a["streak"] or 0)
                upd["best_streak"] = max(p["best_streak"], upd["streak"])
                if a.get("correct"):
                    upd["correct_count"] = p["correct_count"] + 1
                    upd["correct_ms"] = p["correct_ms"] + int(a["elapsed_ms"] or 0)
                run = fast.get(p["user"], 0)
                run = run + 1 if (a.get("correct") and int(a["elapsed_ms"] or 0) < C.FAST_MS) else 0
                fast[p["user"]] = run
                if run >= C.FAST_STREAK and C.FLAG_FAST not in p["flags"]:
                    upd["flags"] = p["flags"] + [C.FLAG_FAST]
        elif scored:
            upd["streak"] = p["streak"] if "shield" in pw_ids else 0
            if PW.miss_points(pw_ids):
                upd["score"] = p["score"] + PW.miss_points(pw_ids)
            fast[p["user"]] = 0
        if pw is not None and scored and pw_ids:
            upd["powers"] = PW.consume(pw, idx)
        if upd:
            repo.update_player(s["name"], p["user"], upd)
            p.update(upd)
    repo.mark_answers_applied(s["name"], idx)
    ranked = board.rank_players(plist)
    steals = []
    if thieves:
        try:                                         # loi danh cap khong duoc chan viec khoa cau
            salt = s["state"].get("salt") or ""
            changed, steals = PW.apply_steals(
                ranked, thieves, lambda u: PW.steal_amount(Q.secret_seed(salt, s["name"], "steal", u, idx)))
            byu = {p["user"]: p for p in plist}
            for user, upd in changed.items():
                repo.update_player(s["name"], user, upd)
                byu[user].update(upd)
            ranked = board.rank_players(plist)       # bang xep hang sau khi trom
        except Exception:
            repo.log_error("dao_tao power steal %s" % s["name"])
            steals = []
    if idx == 0:
        for p in ranked:
            repo.update_player(s["name"], p["user"], {"first_rank": p["rank"]})
    teams = board.rank_teams(plist)
    state = dict(s["state"], fast=fast, steals=steals, **views.board_state(ranked, teams, len(ranked)))
    v = repo.update_session(s["name"], {"phase": C.PHASE_LOCKED, "state": state})
    repo.publish_room(s["name"], v)
    return dict(s, phase=C.PHASE_LOCKED, state=state, version=v)


def _finalize(repo, s):
    """Ve dich: bang cuoi, phong ban, chia giai, cap ve (tran tuan). Chay MOT lan (duoi khoa,
    chuyen pha ended ngay sau)."""
    plist = repo.players(s["name"], locking=True)
    ranked = board.rank_players(plist)
    teams = board.rank_teams(plist)
    scored_total = sum(1 for i, q in enumerate(s["questions"])
                       if q["type"] not in C.UNSCORED_TYPES and i <= s["index"])
    first = {p["user"]: p["first_rank"] for p in plist if p.get("first_rank")}
    awards = prizes.allocate(s["prizes"], ranked, teams, scored_total, board.climbs(ranked, first))
    nick = {p["user"]: p for p in ranked}
    per_user = {}
    for a in awards:
        per_user.setdefault(a["user"], []).append(a)
        p = nick.get(a["user"]) or {}
        a["nickname"] = p.get("nickname") or ""
        a["avatar"] = p.get("avatar") or {}
    for user, rows in per_user.items():
        want = sum(int(r["tickets"]) for r in rows)
        label = "Quiz “%s”: %s" % (s["title"], ", ".join(r["label"] for r in rows))
        try:
            got = ticket_service.grant(repo, user, C.TICKET_QUIZ, s["name"], want, label)
        except Exception:
            repo.log_error("dao_tao ticket grant %s %s" % (s["name"], user))
            got = 0
        for r in rows:
            r["granted"] = got                       # tong ve that su cap cho nguoi nay
    return {"podium": [board.public_row(p) for p in ranked[:3]],
            "top": [board.public_row(p) for p in ranked[:10]],
            "teams": [{"team": t["team"], "score": t["score"], "members": t["members"], "rank": t["rank"],
                       "mvp": (nick.get(t["mvp"]) or {}).get("nickname")} for t in teams],
            "ranks": {p["user"]: p["rank"] for p in ranked},
            "awards": awards, "players": len(ranked), "scored_total": scored_total}


# -------------------------------------------------------------- quan ly nguoi choi --

def manage_player(ctx, repo, name, user, op, nickname=None):
    """op: kick | unkick | rename | reset_device | clear_flags."""
    from ecentric_workspace.dao_tao.domain import profile
    require_host(ctx)
    s = require_found(repo.lock_session(name), "phòng")
    p = require_found(repo.get_player(s["name"], user), "người chơi")
    if op == "kick":
        repo.update_player(s["name"], user, {"kicked": 1})
    elif op == "unkick":
        repo.update_player(s["name"], user, {"kicked": 0})
    elif op == "rename":
        repo.update_player(s["name"], user, {"nickname": profile.clean_nickname(nickname)})
    elif op == "reset_device":
        repo.update_player(s["name"], user, {"device": ""})
    elif op == "clear_flags":
        repo.update_player(s["name"], user, {"flags": []})
    else:
        raise QuizError("Thao tác không hợp lệ.")
    v = repo.update_session(s["name"], {"state": dict(s["state"], player_count=repo.count_players(s["name"]))})
    repo.publish_room(s["name"], v)
    return {"user": p["user"], "op": op}

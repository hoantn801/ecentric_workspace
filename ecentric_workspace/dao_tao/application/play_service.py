# Copyright (c) 2026, eCentric and contributors
"""Phong quiz phia NGUOI CHOI: vao phong bang ma, tao nhan vat, xem trang thai, tra loi.

Chong gian lan o day (muc bao ve - xem constants GUARD_*):
  * Thoi gian = luc SERVER nhan (repo.now_ms), khong tin dong ho may.
  * Moi nguoi tra loi mot cau MOT lan (khoa chinh EC Quiz Answer) - bam lan 2 / gui lai bi tu choi.
  * Nhan cau tra loi DUOI KHOA phong, kiem lai pha + cau + gio tren ban moi nhat - khong ai tra
    loi lot sau khi cau da khoa (diem se khong duoc cong ma van hien "da chot").
  * Chuan tro len: 1 nguoi 1 thiet bi (ma thiet bi luu localStorage), chan trinh duyet tu dong
    (navigator.webdriver), co tra loi nhanh bat thuong (o room_service._lock_question).
  * Nghiem: ghi nhan roi man hinh (bao tu trang) -> co cho nguoi dan xem; khong tu tru diem.
"""
from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.application import room_service, views
from ecentric_workspace.dao_tao.application.access import require_found
from ecentric_workspace.dao_tao.domain import powers as PW, profile, questions as Q, room, scoring, settings as S
from ecentric_workspace.dao_tao.domain.errors import QuizError, QuizNotFound

MSG_NO_ROOM = "Không có phòng nào đang mở với mã này. Kiểm tra lại 6 số trên màn chiếu."
MSG_OTHER_DEVICE = ("Bạn đang chơi phòng này trên một thiết bị khác. Nhờ người dẫn bấm "
                    "“Cho đổi máy” nếu bạn vừa đổi điện thoại.")
MSG_AUTOMATION = "Phòng này không cho trình duyệt điều khiển tự động. Mở bằng điện thoại / trình duyệt thường nhé."
MSG_KICKED = "Người dẫn đã mời bạn ra khỏi phòng."


def _clean_code(code):
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != C.CODE_LEN:
        raise QuizError("Mã phòng gồm %d số." % C.CODE_LEN)
    return code


def _session_by_code(repo, code):
    s = repo.session_by_code(_clean_code(code))
    if not s:
        raise QuizNotFound(MSG_NO_ROOM)
    return s


def _device_ok(s, player, device):
    return not S.one_device(s["settings"]) or not player.get("device") or player["device"] == (device or "")


def my_profile(ctx, repo):
    prof = repo.get_profile(ctx.user)
    if prof:
        return {"nickname": prof["nickname"], "avatar": profile.clean_avatar(prof["avatar"]), "saved": True}
    emp = repo.employee(ctx.user)
    return {"nickname": profile.default_nickname(emp.get("employee_name"), ctx.user),
            "avatar": profile.avatar_for(ctx.user), "saved": False}


def join(ctx, repo, code, device="", automation=False):
    s0 = _session_by_code(repo, code)
    # Khoa phong TRUOC moi doc/ghi khac: cung thu tu khoa voi answer / auto_lock (chong deadlock)
    # va lay state_json moi nhat (khong ghi de bang ban cu trong Redis).
    s = repo.lock_session(s0["name"])
    if not s or s["phase"] not in C.LIVE_PHASES:
        raise QuizNotFound(MSG_NO_ROOM)
    st = s["settings"]
    if automation and S.block_automation(st):
        raise QuizError(MSG_AUTOMATION)
    device = str(device or "")[:64]
    p = repo.get_player(s["name"], ctx.user)
    if p:
        if p.get("kicked"):
            raise QuizError(MSG_KICKED)
        if not _device_ok(s, p, device):
            if C.FLAG_DEVICE not in p["flags"]:
                repo.update_player(s["name"], ctx.user, {"flags": p["flags"] + [C.FLAG_DEVICE]})
            raise QuizError(MSG_OTHER_DEVICE)
        if not p.get("device") and device:
            repo.update_player(s["name"], ctx.user, {"device": device})
        return state(ctx, repo, s["code"], device)
    if repo.count_players(s["name"]) >= C.MAX_PLAYERS:
        raise QuizError("Phòng đã đủ %d người." % C.MAX_PLAYERS)
    prof = my_profile(ctx, repo)
    emp = repo.employee(ctx.user)
    nick = prof["nickname"] if st.get("allow_nick", True) else profile.default_nickname(
        emp.get("employee_name"), ctx.user)
    try:
        repo.insert_player({"session": s["name"], "user": ctx.user, "nickname": nick,
                            "avatar": prof["avatar"] if st.get("allow_avatar", True) else profile.avatar_for(ctx.user),
                            "department": emp.get("department") or "", "device": device,
                            "joined_at": repo.now()})
    except Exception as e:                            # hai tab vao cung luc -> mot dong thang
        if not repo.is_duplicate(e):
            raise
    v = repo.update_session(s["name"], {"state": dict(s["state"], player_count=repo.count_players(s["name"]))})
    repo.publish_room(s["name"], v)
    out = state(ctx, repo, s["code"], device)
    out["first_join"] = not prof["saved"]
    return out


def set_profile(ctx, repo, code, nickname=None, avatar=None):
    """Doi ten / nhan vat. Luu theo tai khoan (dung lai lan sau) + cap nhat trong phong."""
    s0 = _session_by_code(repo, code)
    s = repo.lock_session(s0["name"])
    st = s["settings"]
    p = require_found(repo.get_player(s["name"], ctx.user), "người chơi")
    cur = my_profile(ctx, repo)
    nick = profile.clean_nickname(nickname) if (nickname is not None and st.get("allow_nick", True)) else p["nickname"]
    av = profile.clean_avatar(avatar) if (avatar is not None and st.get("allow_avatar", True)) else p["avatar"]
    repo.update_player(s["name"], ctx.user, {"nickname": nick, "avatar": av})
    repo.save_profile(ctx.user, nick if st.get("allow_nick", True) else cur["nickname"],
                      av if st.get("allow_avatar", True) else cur["avatar"])
    v = repo.update_session(s["name"], {})          # chi tang phien ban - khong ghi lai state
    repo.publish_room(s["name"], v)
    return state(ctx, repo, s["code"])


def state(ctx, repo, code, device=None):
    s = _session_by_code(repo, code) if code else None
    s = room_service.auto_lock(repo, s)
    p = repo.get_player(s["name"], ctx.user)
    if p and device is not None and device != "" and not _device_ok(s, p, device):
        raise QuizError(MSG_OTHER_DEVICE)
    a = repo.get_answer(s["name"], s["index"], ctx.user) if p else None
    return views.player_view(s, p, a, repo.now_ms())


def ended_state(ctx, repo, session):
    """Phong da ket thuc (ma phong khong con tra cuu duoc) - xem lai ket qua cua minh."""
    s = require_found(repo.get_session(session), "phòng")
    p = repo.get_player(s["name"], ctx.user)
    if not p:
        raise QuizNotFound("Bạn không chơi phòng này.")
    return views.player_view(s, p, None, repo.now_ms())


def answer(ctx, repo, code, qid, payload, device=""):
    s0 = _session_by_code(repo, code)
    s = repo.lock_session(s0["name"])               # moi kiem tra duoi khoa, tren ban moi nhat
    now = repo.now_ms()
    if s["phase"] != C.PHASE_QUESTION or not s["questions"]:
        raise QuizError("Câu này đã khoá.")
    q = s["questions"][s["index"]]
    if qid != q["id"]:
        raise QuizError("Câu này đã qua, màn hình sẽ tự chuyển.")
    if not room.accepting(s["phase"], now, s["deadline_ms"]):
        raise QuizError("Hết giờ rồi.")              # lan doc ke tiep se tu khoa (auto_lock)
    if now < s["opened_ms"] + C.LEAD_IN_SEC * 1000:
        raise QuizError("Chưa tới lúc trả lời.")
    p = repo.get_player(s["name"], ctx.user)
    if not p:
        raise QuizError("Bạn chưa vào phòng.")
    if p.get("kicked"):
        raise QuizError(MSG_KICKED)
    if not _device_ok(s, p, device):
        raise QuizError(MSG_OTHER_DEVICE)
    clean = Q.clean_answer(q, payload)
    ratio = Q.grade(q, clean)
    elapsed = room.elapsed_ms(s["opened_ms"], now)
    is_last = s["index"] + 1 >= len(s["questions"])
    sc = scoring.score_answer(ratio, elapsed, q["time"] * 1000, p["streak"], is_last, s["settings"])
    if PW.enabled(s["settings"]):
        try:                                        # loi power-up khong duoc chan viec tra loi
            ids = PW.effective(PW.clean_state(p.get("powers")), s["index"])
            if ids:
                sc = scoring.score_answer(ratio, PW.elapsed_for_score(ids, elapsed), q["time"] * 1000,
                                          p["streak"], is_last, s["settings"])
                sc = PW.adjust(ids, sc, ratio, p["streak"], q["type"])
        except Exception:
            repo.log_error("dao_tao power answer %s %s" % (s["name"], ctx.user))
            sc = scoring.score_answer(ratio, elapsed, q["time"] * 1000, p["streak"], is_last, s["settings"])
    try:
        repo.insert_answer({"session": s["name"], "user": ctx.user, "q_index": s["index"], "qid": q["id"],
                            "answer": clean, "received_ms": now, "elapsed_ms": elapsed,
                            "ratio": ratio, "correct": 1 if sc["correct"] else 0,
                            "points": sc["points"], "streak": sc["streak"], "applied": 0})
    except Exception as e:
        if repo.is_duplicate(e):
            raise QuizError("Bạn đã trả lời câu này rồi.")
        raise
    room_service.lock_if_all_answered(repo, s)
    return {"ok": True}


def report(ctx, repo, code, kind):
    """Muc Nghiem: trang bao roi man hinh -> gan co (khong tru diem)."""
    s = _session_by_code(repo, code)
    if kind != C.FLAG_BLUR or not S.strict(s["settings"]):
        return {"ok": False}
    p = repo.get_player(s["name"], ctx.user)
    if p and C.FLAG_BLUR not in p["flags"]:
        repo.update_player(s["name"], ctx.user, {"flags": p["flags"] + [C.FLAG_BLUR]})
    return {"ok": True}


def live_card(ctx, repo):
    """The noi "Quiz dang mo" (ec_quiz_live.bundle.js, moi trang ERP + app HR). Danh sach phong
    giong nhau cho moi nguoi -> cache 15 giay chung; tat bang site_config ec_quiz_card_disabled."""
    if repo.flag("ec_quiz_card_disabled"):
        return {"rooms": []}
    rows = repo.cache_get(C.CACHE_CARD)
    if rows is None:
        rows = [{"code": r["code"], "title": r["title"], "phase": r["phase"]} for r in lobby_rooms(ctx, repo)][:3]
        repo.cache_set(C.CACHE_CARD, rows, C.CACHE_CARD_TTL)
    return {"rooms": rows}


def lobby_rooms(ctx, repo):
    """Phong dang mo cho trang /quiz (ai cung thay - ma phong von hien cong khai tren man chieu)."""
    import datetime
    since = repo.now() - datetime.timedelta(hours=C.ROOM_STALE_HOURS)
    rows = repo.live_sessions(since)
    names = repo.full_names([r["host"] for r in rows])
    return [{"code": r["code"], "title": r["title"], "phase": r["phase"],
             "host": names.get(r["host"], r["host"]), "created": r["created"]} for r in rows]


def history(ctx, repo):
    """"Quiz cua toi": cac phong da choi + hang + giai, va ve tuan."""
    from ecentric_workspace.dao_tao.application import ticket_service
    rows = []
    for r in repo.played(ctx.user):
        res = None
        if r["phase"] == C.PHASE_ENDED:
            s = repo.get_session(r["session"])
            res = (s or {}).get("results") or {}
        rows.append({"session": r["session"], "title": r["title"], "phase": r["phase"],
                     "ended_at": r["ended_at"], "score": r["score"], "nickname": r["nickname"],
                     "rank": (res or {}).get("ranks", {}).get(ctx.user),
                     "players": (res or {}).get("players"),
                     "awards": [{"label": a["label"], "gift": a["gift"], "tickets": a["tickets"]}
                                for a in (res or {}).get("awards") or [] if a.get("user") == ctx.user]})
    return {"played": rows, "tickets": ticket_service.summary(repo, ctx.user)}


# ------------------------------------------------------------------- power-up --

def _power_ctx(ctx, repo, code, device):
    s0 = _session_by_code(repo, code)
    s = repo.lock_session(s0["name"])               # moi thay doi tui / diem duoi khoa phong
    if not PW.enabled(s["settings"]):
        raise QuizError("Phòng này không bật power-up.")
    p = repo.get_player(s["name"], ctx.user)
    if not p:
        raise QuizError("Bạn chưa vào phòng.")
    if p.get("kicked"):
        raise QuizError(MSG_KICKED)
    if not _device_ok(s, p, device):
        raise QuizError(MSG_OTHER_DEVICE)
    return s, p


def pick_power(ctx, repo, code, power, device=""):
    """Chon 1 trong 3 skill duoc moi (hoac "skip"). Tui vang cong diem ngay."""
    s, p = _power_ctx(ctx, repo, code, device)
    answered = bool(repo.get_answer(s["name"], s["index"], ctx.user)) if s["phase"] == C.PHASE_QUESTION else False
    k = views.offer_index(s, answered)
    if k is None:
        raise QuizError("Chưa tới lúc chọn power-up.")
    st = PW.clean_state(p.get("powers"))
    if str(k) in st["picked"]:
        raise QuizError("Bạn đã chọn power-up lượt này rồi.")
    power = str(power or "")
    if power != PW.SKIP:
        if len(st["bag"]) >= PW.BAG_MAX:
            raise QuizError("Túi đã đủ %d skill - dùng bớt rồi chọn tiếp nhé." % PW.BAG_MAX)
        if power not in views.offer_ids(s, ctx.user, k):
            raise QuizError("Skill này không có trong lượt mời của bạn.")
    st["picked"][str(k)] = power
    upd = {}
    if power == "gold":
        st["used"].append(power)
        upd["score"] = p["score"] + PW.GOLD_POINTS
    elif power != PW.SKIP:
        st["bag"].append(power)
    upd["powers"] = st
    repo.update_player(s["name"], ctx.user, upd)
    return state(ctx, repo, s["code"], device)


def use_power(ctx, repo, code, power, device=""):
    """Kich hoat skill trong tui cho CAU DANG MO (truoc khi tra loi)."""
    s, p = _power_ctx(ctx, repo, code, device)
    if s["phase"] != C.PHASE_QUESTION:
        raise QuizError("Chỉ dùng skill khi câu hỏi đang mở.")
    q = s["questions"][s["index"]]
    if q["type"] in C.UNSCORED_TYPES:
        raise QuizError("Câu này không tính điểm - để dành skill cho câu sau nhé.")
    if repo.get_answer(s["name"], s["index"], ctx.user):
        raise QuizError("Bạn đã trả lời câu này rồi.")
    st = PW.clean_state(p.get("powers"))
    if power not in st["bag"]:
        raise QuizError("Skill này không có trong túi của bạn.")
    repo.update_player(s["name"], ctx.user, {"powers": PW.activate(st, power, s["index"])})
    return state(ctx, repo, s["code"], device)

# Copyright (c) 2026, eCentric and contributors
"""Dung goi du lieu gui xuong may nguoi choi / may chieu tu trang thai phong. Khong cham DB.

Nguyen tac (chong gian lan): may NGUOI CHOI chi nhan
  * pha question: cau hoi qua `questions.public_view` (khong dap an) + so ms con lai tinh o server
  * pha locked: "da chot" - KHONG dung sai
  * pha reveal tro di: dap an, dung / sai / diem CUA MINH
May CHIEU (nguoi dan) cung khong nhan dap an truoc pha reveal - man hinh chieu nam trong phong,
ai cung nhin duoc tab dev tools cua laptop nguoi dan neu de ho.
"""
from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.domain import board, powers as PW, questions as Q, room, settings as S

TOP_N = 5


def remaining_ms(s, now_ms):
    if s["phase"] != C.PHASE_QUESTION:
        return 0
    return max(0, s["deadline_ms"] - now_ms)


def _timing(s, now_ms):
    q = s["questions"][s["index"]]
    lead = max(0, s["opened_ms"] + C.LEAD_IN_SEC * 1000 - now_ms) if s["phase"] == C.PHASE_QUESTION else 0
    return {"remaining_ms": remaining_ms(s, now_ms), "lead_ms": lead, "limit_ms": q["time"] * 1000}


def seed_for(s, who):
    """Hat giong xao BI MAT: HMAC(muoi luu trong state_json - khong bao gio gui xuong may)."""
    return Q.secret_seed(s["state"].get("salt") or "", s["name"], who)


def _q_for_player(s, user):
    q = s["questions"][s["index"]]
    st = s["settings"]
    v = Q.public_view(q, seed_for(s, user), S.shuffles_options(st))
    if not st.get("show_on_phone", True) and q["type"] in (C.Q_SINGLE, C.Q_MULTI, C.Q_TRUEFALSE, C.Q_POLL):
        # Che do "chi o mau": may chi co o mau + chu cai, nhin cau hoi tren may chieu.
        v["text"] = ""
        v["media"] = None
        v["options"] = [{"id": o["id"], "text": ""} for o in v["options"]]
        v["tiles_only"] = True
    return v


def common(s, now_ms):
    st = s["settings"]
    total = len(s["questions"])
    out = {"session": s["name"], "code": s["code"], "title": s["title"], "phase": s["phase"],
           "version": s["version"], "index": s["index"], "total": total,
           "is_last": s["index"] + 1 >= total, "server_ms": now_ms,
           "rules": {"mode": st.get("mode"), "show_on_phone": st.get("show_on_phone", True),
                     "allow_nick": st.get("allow_nick", True), "allow_avatar": st.get("allow_avatar", True),
                     "guard": st.get("guard"), "strict": S.strict(st), "one_device": S.one_device(st),
                     "last_double": st.get("last_double", True), "power_ups": PW.enabled(st)}}
    if s["phase"] in (C.PHASE_QUESTION, C.PHASE_LOCKED, C.PHASE_REVEAL, C.PHASE_BOARD):
        out.update(_timing(s, now_ms))
    return out


def offer_index(s, answered):
    """Luot moi power-up dang mo (chi so cau vua cong bo) hoac None. Mo trong luc cong bo / bang
    xep hang cua cau 5, 10, ... va ca cau ke tiep (truoc khi tra loi) cho ai chua kip chon."""
    if not PW.enabled(s["settings"]):
        return None
    total, i = len(s["questions"]), s["index"]
    if s["phase"] in (C.PHASE_REVEAL, C.PHASE_BOARD) and PW.offer_at(i, total):
        return i
    if s["phase"] == C.PHASE_QUESTION and not answered and i >= 1 and PW.offer_at(i - 1, total):
        return i - 1
    return None


def offer_ids(s, user, k):
    return PW.offer(Q.secret_seed(s["state"].get("salt") or "", s["name"], "power", user, k))


def _power_view(s, player, answered):
    st = PW.clean_state(player.get("powers"))
    k = offer_index(s, answered)
    out = {"bag": [PW.info(i) for i in st["bag"]], "bag_max": PW.BAG_MAX,
           "active": [PW.info(i) for i in PW.effective(st, s["index"])] if s["phase"] == C.PHASE_QUESTION else [],
           "offer": None, "picked": None, "full": len(st["bag"]) >= PW.BAG_MAX}
    if k is not None:
        got = st["picked"].get(str(k))
        if got:
            out["picked"] = PW.info(got) if got != PW.SKIP else {"id": PW.SKIP, "label": "Bỏ qua"}
        elif not out["full"]:
            out["offer"] = [PW.info(i) for i in offer_ids(s, player["user"], k)]
    return out


def board_rows(s, n=TOP_N):
    return (s["state"].get("board") or [])[:n]


def player_view(s, player, answer, now_ms):
    """Trang thai cho MOT nguoi choi. player = dong EC Quiz Player (hoac None neu chua vao)."""
    out = common(s, now_ms)
    if not player:
        out["joined"] = False
        return out
    ranks = s["state"].get("ranks") or {}
    out["joined"] = True
    out["kicked"] = bool(player.get("kicked"))
    ph = s["phase"]
    score, streak, rank = player["score"], player["streak"], ranks.get(player["user"])
    if ph in (C.PHASE_QUESTION, C.PHASE_LOCKED):
        # Diem / chuoi / hang da cong luc khoa cau - chua cong bo thi hien so CU (khong lo dung sai).
        if answer and answer.get("applied"):
            score -= int(answer.get("points") or 0)
        if ph == C.PHASE_LOCKED:
            streak, rank = None, None
    out["me"] = {"nickname": player["nickname"], "avatar": player["avatar"], "email": player["user"],
                 "department": player.get("department") or "", "score": score,
                 "streak": streak, "rank": rank, "players": s["state"].get("player_count") or 0}
    if ph == C.PHASE_QUESTION:
        out["answered"] = bool(answer)
        if not answer:
            out["question"] = _q_for_player(s, player["user"])
            if PW.enabled(s["settings"]):
                gone = PW.eliminated(s["questions"][s["index"]],
                                     PW.effective(PW.clean_state(player.get("powers")), s["index"]),
                                     seed_for(s, "elim|" + player["user"]))
                if gone and out["question"].get("options"):
                    # Giu dung vi tri (cung mau / chu cai voi may chieu), chi danh dau o bi loai.
                    out["question"]["options"] = [dict(o, gone=True) if o["id"] == gone else o
                                                  for o in out["question"]["options"]]
    elif ph == C.PHASE_LOCKED:
        out["answered"] = bool(answer)
    elif ph in (C.PHASE_REVEAL, C.PHASE_BOARD):
        q = s["questions"][s["index"]]
        out["answered"] = bool(answer)
        out["result"] = {"scored": q["type"] not in C.UNSCORED_TYPES,
                         "correct": bool(answer and answer.get("correct")),
                         "partial": bool(answer and not answer.get("correct") and (answer.get("ratio") or 0) > 0),
                         "points": int(answer["points"]) if answer else 0,
                         "streak": player["streak"]}
        if ph == C.PHASE_REVEAL:
            out["question"] = Q.public_view(q, seed_for(s, player["user"]), S.shuffles_options(s["settings"]))
            out["reveal"] = Q.reveal_view(q)
            out["my_answer"] = answer.get("answer") if answer else None
        else:
            out["board"] = board_rows(s)
    if PW.enabled(s["settings"]) and ph in (C.PHASE_QUESTION, C.PHASE_REVEAL, C.PHASE_BOARD):
        out["power"] = _power_view(s, player, bool(answer))
    if ph == C.PHASE_ENDED:
        res = s.get("results") or {}
        out["final"] = {"podium": res.get("podium") or [], "teams": (res.get("teams") or [])[:6],
                        "my_rank": (res.get("ranks") or {}).get(player["user"]),
                        "my_score": player["score"], "players": res.get("players") or 0,
                        "awards": [a for a in res.get("awards") or [] if a.get("user") == player["user"]]}
    return out


def host_view(s, players, answered_count, now_ms):
    """May chieu + bang nguoi dan. players = toan bo dong nguoi choi (da doc o service)."""
    out = common(s, now_ms)
    st = s["settings"]
    active = [p for p in players if not p.get("kicked")]
    out["players"] = len(active)
    out["answered"] = answered_count
    out["next_action"] = room.next_action(s["phase"], s["index"], len(s["questions"]), st.get("board"))
    out["settings"] = st
    out["lobby"] = [{"nickname": p["nickname"], "email": p["user"], "avatar": p["avatar"],
                     "department": p.get("department") or "", "kicked": p.get("kicked"),
                     "flags": p.get("flags") or [], "device": bool(p.get("device"))}
                    for p in players[-C.MAX_PLAYERS:]]
    out["flags"] = [{"nickname": p["nickname"], "email": p["user"], "flags": p["flags"]}
                    for p in players if p.get("flags")]
    if s["phase"] in (C.PHASE_QUESTION, C.PHASE_LOCKED, C.PHASE_REVEAL, C.PHASE_BOARD):
        q = s["questions"][s["index"]]
        out["question"] = Q.public_view(q, seed_for(s, "__host__"), False)
        if s["phase"] in (C.PHASE_REVEAL, C.PHASE_BOARD):
            out["reveal"] = Q.reveal_view(q)
            out["tally"] = s["state"].get("tally") or {}
    if s["phase"] in (C.PHASE_REVEAL, C.PHASE_BOARD):
        out["board"] = board_rows(s)
        if st.get("mode") == C.MODE_TEAM:
            out["teams"] = (s["state"].get("teams") or [])[:6]
    if s["phase"] in (C.PHASE_REVEAL, C.PHASE_BOARD) and PW.enabled(st) and PW.offer_at(s["index"], len(s["questions"])):
        k = str(s["index"])
        out["power_open"] = {"picked": sum(1 for p in active if k in ((p.get("powers") or {}).get("picked") or {}))}
    if s["phase"] == C.PHASE_ENDED:
        out["final"] = s.get("results") or {}
    return out


def board_state(ranked, teams, total_players):
    """Phan "bang xep hang" luu vao state_json luc khoa cau (nguoi choi doc tu Redis, khong dem lai)."""
    return {"board": [board.public_row(p) for p in ranked[:10]],
            "ranks": {p["user"]: p["rank"] for p in ranked},
            "teams": [{"team": t["team"], "score": t["score"], "members": t["members"], "rank": t["rank"]}
                      for t in teams[:12]],
            "player_count": total_players}

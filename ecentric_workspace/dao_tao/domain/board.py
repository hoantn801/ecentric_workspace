# Copyright (c) 2026, eCentric and contributors
"""Bang xep hang nguoi choi + duong dua phong ban. Thuan Python.

Nguoi choi: diem giam dan -> tong thoi gian tra loi DUNG tang dan -> vao phong som hon.
Phong ban (Hoan chot): doi = phong ban tren ERP; diem doi = TRUNG BINH diem moi nguoi (khong
phai tong - phong dong nguoi khong tu thang); phong duoi 4 nguoi choi gop vao "Van phong".
Ket thuc game LUON co ca top nguoi choi va top phong ban (ke ca kieu thi ca nhan).
"""
from ecentric_workspace.dao_tao import constants as C


def _key(p):
    return (-int(p.get("score") or 0), int(p.get("correct_ms") or 0), str(p.get("joined_at") or ""),
            p.get("user") or "")


def rank_players(players):
    """-> ban sao da sap, moi dong them `rank` (1..n). Bo nguoi bi moi ra (kicked)."""
    rows = sorted([dict(p) for p in players if not p.get("kicked")], key=_key)
    for i, p in enumerate(rows):
        p["rank"] = i + 1
    return rows


def team_of(players, min_size=C.TEAM_MIN_SIZE):
    """user -> ten doi. Phong it hon `min_size` nguoi choi (ke ca "chua co phong") -> Van phong."""
    count = {}
    for p in players:
        if p.get("kicked"):
            continue
        d = p.get("department") or C.TEAM_UNKNOWN
        count[d] = count.get(d, 0) + 1
    out = {}
    for p in players:
        d = p.get("department") or C.TEAM_UNKNOWN
        out[p["user"]] = d if count.get(d, 0) >= min_size else C.TEAM_MERGED
    return out


def rank_teams(players, min_size=C.TEAM_MIN_SIZE):
    """-> [{team, score (trung binh), members, total, mvp: user, rank}] da sap."""
    tmap = team_of(players, min_size)
    teams = {}
    for p in rank_players(players):
        t = teams.setdefault(tmap[p["user"]], {"team": tmap[p["user"]], "total": 0, "members": 0,
                                               "mvp": None, "mvp_score": -1, "users": []})
        t["total"] += int(p.get("score") or 0)
        t["members"] += 1
        t["users"].append(p["user"])
        if int(p.get("score") or 0) > t["mvp_score"]:      # rank_players da sap -> nguoi dau
            t["mvp"], t["mvp_score"] = p["user"], int(p.get("score") or 0)
    rows = []
    for t in teams.values():
        t["score"] = int(round(t["total"] / float(t["members"]))) if t["members"] else 0
        t.pop("mvp_score", None)
        rows.append(t)
    rows.sort(key=lambda t: (-t["score"], -t["members"], t["team"]))
    for i, t in enumerate(rows):
        t["rank"] = i + 1
    return rows


def climbs(ranked, first_ranks):
    """{user: so bac leo} = hang sau cau dau - hang cuoi. Chi tinh nguoi co hang sau cau dau."""
    out = {}
    for p in ranked:
        fr = first_ranks.get(p["user"])
        if fr:
            out[p["user"]] = int(fr) - int(p["rank"])
    return out


def public_row(p, show_email=True):
    row = {"nickname": p.get("nickname") or "", "avatar": p.get("avatar") or {},
           "score": int(p.get("score") or 0), "rank": p.get("rank"),
           "correct": int(p.get("correct_count") or 0), "streak": int(p.get("streak") or 0)}
    if show_email:
        row["email"] = p.get("user")
    return row

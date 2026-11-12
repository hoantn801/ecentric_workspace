# Copyright (c) 2026, eCentric and contributors
"""Phan thuong tu cai theo tung dong (Hoan 12/11). Thuan Python.

Moi dong: pham vi (nguoi choi / phong ban), ai nhan, so ve 0-3, qua kem (chu tu do, goi y tu
GIFT_SUGGESTIONS). Mot nguoi nhan duoc nhieu dong neu du dieu kien (vd Hang 1 + Dung tu 60% +
Doi nhat). Ve con bi tran 3 ve / nguoi / tuan o `tickets.grant` - o day chi chia.
Nguoi 0 diem khong nhan giai theo hang (phong vang nguoi, 1 nguoi vao roi bo di).
"""
from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.domain.errors import QuizError

_GIFT_MAX = 60


def clean_prizes(raw):
    if raw in (None, ""):
        return [dict(p) for p in C.DEFAULT_PRIZES]
    if not isinstance(raw, list):
        raise QuizError("Phần thưởng không hợp lệ.")
    if len(raw) > C.MAX_PRIZES:
        raise QuizError("Tối đa %d dòng phần thưởng." % C.MAX_PRIZES)
    out = []
    for i, r in enumerate(raw):
        if not isinstance(r, dict):
            continue
        scope = r.get("scope")
        allowed = C.PLAYER_RANKS if scope == C.SCOPE_PLAYER else C.TEAM_RANKS if scope == C.SCOPE_TEAM else ()
        if r.get("rank") not in allowed:
            raise QuizError("Dòng thưởng %d: chưa chọn ai nhận." % (i + 1))
        try:
            tickets = int(r.get("tickets") or 0)
        except (TypeError, ValueError):
            tickets = 0
        tickets = min(max(tickets, 0), C.TICKETS_MAX_PER_PRIZE)
        gift = " ".join(str(r.get("gift") or "").split())[:_GIFT_MAX]
        if not tickets and not gift:
            raise QuizError("Dòng thưởng %d: cần ít nhất 1 vé hoặc 1 món quà." % (i + 1))
        out.append({"scope": scope, "rank": r["rank"], "tickets": tickets, "gift": gift})
    return out


def _award(row, user, extra=None):
    a = {"user": user, "rank": row["rank"], "scope": row["scope"],
         "label": C.RANK_LABELS.get(row["rank"], row["rank"]), "tickets": row["tickets"],
         "gift": row["gift"]}
    if extra:
        a.update(extra)
    return a


def allocate(prizes, ranked, teams, scored_total, climbs=None):
    """ranked = board.rank_players(...), teams = board.rank_teams(...).
    -> [{user, rank, scope, label, tickets, gift, team?}] theo thu tu dong thuong."""
    climbs = climbs or {}
    out = []
    by_rank = {p["rank"]: p for p in ranked}
    for row in prizes:
        r = row["rank"]
        if row["scope"] == C.SCOPE_PLAYER:
            if r in (C.RANK_1, C.RANK_2, C.RANK_3):
                p = by_rank.get({C.RANK_1: 1, C.RANK_2: 2, C.RANK_3: 3}[r])
                if p and int(p.get("score") or 0) > 0:
                    out.append(_award(row, p["user"]))
            elif r == C.RANK_4_10:
                for n in range(4, 11):
                    p = by_rank.get(n)
                    if p and int(p.get("score") or 0) > 0:
                        out.append(_award(row, p["user"]))
            elif r == C.RANK_PASS and scored_total > 0:
                for p in ranked:
                    if int(p.get("correct_count") or 0) >= C.PASS_RATIO * scored_total - 1e-9:
                        out.append(_award(row, p["user"]))
            elif r == C.RANK_CLIMB:
                best = None
                for p in ranked:                         # ranked da sap: hoa thi hang cao hon
                    c = climbs.get(p["user"], 0)
                    if c > 0 and (best is None or c > best[1]):
                        best = (p["user"], c)
                if best:
                    out.append(_award(row, best[0], {"climb": best[1]}))
        else:
            if r in (C.TEAM_1, C.TEAM_2):
                t = next((t for t in teams if t["rank"] == (1 if r == C.TEAM_1 else 2)), None)
                if t and t["score"] > 0:
                    for u in t["users"]:
                        out.append(_award(row, u, {"team": t["team"]}))
            elif r == C.TEAM_MVP:
                for t in teams:
                    if t.get("mvp") and t["score"] > 0:
                        out.append(_award(row, t["mvp"], {"team": t["team"]}))
    return out


def summary(prizes, players_count, teams_count):
    """Tam tinh cho trinh soan: tong ve toi da + so qua se phat (gia dinh du nguoi)."""
    tickets, gifts = 0, 0
    for row in prizes:
        r = row["rank"]
        n = {C.RANK_1: 1, C.RANK_2: 1, C.RANK_3: 1, C.RANK_4_10: 7, C.RANK_CLIMB: 1,
             C.RANK_PASS: players_count, C.TEAM_MVP: teams_count}.get(r)
        if n is None:   # doi nhat / nhi: trung binh moi doi
            n = int(round(players_count / float(max(teams_count, 1))))
        n = min(n, players_count)
        tickets += n * row["tickets"]
        gifts += n if row["gift"] else 0
    return {"tickets": tickets, "gifts": gifts}

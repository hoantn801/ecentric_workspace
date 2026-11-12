# Copyright (c) 2026, eCentric and contributors
"""Quay so tuan cua trang Hoc (tab Phan thuong) + trang Quan ly bai hoc (tab Quay so tuan).

Luat (Hoan chot 12/11/2026): moi ve = mot luot rieng; so khong ai giu -> qua de lai; gio quay
mac dinh 16:00 thu Sau, Ban dao tao doi duoc; qua cai theo dong nhu /khao-sat.
Luot quay cua tuan tu tao lan dau co nguoi mo (chua cai qua thi toi gio quay "khong co qua").
Chon / bo so va quay deu chay DUOI KHOA dong luot quay (repo.lock_draw) - hai nguoi khong
giu trung mot so, va quay chi chay mot lan (job moi phut + nut "Quay ngay").
"""
import random

from ecentric_workspace.dao_tao.infrastructure import store as default_repo

from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.application.access import require_found, require_host
from ecentric_workspace.dao_tao.domain import draw as DR, tickets
from ecentric_workspace.dao_tao.domain.errors import QuizError


def _week(repo):
    return tickets.week_start(repo.now())


def current(repo, week=None):
    """Luot quay cua tuan (tao neu chua co)."""
    ws = week or _week(repo)
    name = repo.draw_name(ws)
    d = repo.get_draw(name)
    if d:
        return d
    try:
        repo.insert_draw({"title": "Quay số tuần · " + tickets.week_label(ws), "week_start": ws,
                          "draw_at": DR.default_draw_at(ws), "range": DR.RANGE_DEFAULT,
                          "status": C.DRAW_OPEN, "prizes": []})
    except Exception as e:                       # hai nguoi mo cung luc -> mot dong thang
        if not repo.is_duplicate(e):
            raise
    return repo.get_draw(name)


def _dt(v):
    import datetime
    if isinstance(v, datetime.datetime):
        return v
    return datetime.datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S")


def _view(repo, d, user, names=None):
    now = repo.now()
    draw_at = _dt(d["draw_at"])
    mine = repo.draw_numbers(d["name"], user)
    my_tickets = repo.week_tickets(d["week_start"]).get(user, 0) if user else 0
    taken = [r["number"] for r in repo.draw_numbers(d["name"])]
    res = d.get("results")
    out = {"name": d["name"], "title": d["title"], "status": d["status"], "draw_at": str(draw_at),
           "lock_at": str(DR.lock_at(draw_at)), "range": d["range"], "prizes": d["prizes"],
           "open": d["status"] == C.DRAW_OPEN and now < DR.lock_at(draw_at),
           "tickets": my_tickets,
           "mine": [{"number": r["number"], "auto": int(r["auto"] or 0), "active": r["slot"] < my_tickets}
                    for r in mine],
           "taken": sorted(taken) if d["range"] <= 300 else [], "taken_count": len(taken),
           "server_now": str(now)}
    if res is not None:
        names = names or repo.full_names([r["user"] for r in res if r.get("user")])
        labels = {p["id"]: p["label"] for p in d["prizes"]}
        out["results"] = [{"number": r["number"], "prize": labels.get(r["prize"], ""), "rank": r["rank"],
                           "winner": names.get(r["user"], "") if r.get("user") else "", "me": r.get("user") == user}
                          for r in res]
    return out


def hub(ctx, repo):
    return _view(repo, current(repo), ctx.user)


def pick(ctx, repo, number=None, rng=None):
    """Chon mot so cho ve CHUA co so (number=None -> may chon ngau nhien mot so con trong)."""
    d = current(repo)
    d = repo.lock_draw(d["name"])
    if d["status"] != C.DRAW_OPEN or repo.now() >= DR.lock_at(_dt(d["draw_at"])):
        raise QuizError("Đã khoá chọn số tuần này.")
    have = repo.week_tickets(d["week_start"]).get(ctx.user, 0)
    mine = repo.draw_numbers(d["name"], ctx.user)
    used = {r["slot"] for r in mine}
    free_slots = [i for i in range(have) if i not in used]
    if not free_slots:
        raise QuizError("Bạn đã chọn số cho hết vé tuần này." if have else "Bạn chưa có vé tuần này.")
    taken = {r["number"] for r in repo.draw_numbers(d["name"], locking=True)}
    if number in (None, "", 0, "0"):
        free = [n for n in range(1, d["range"] + 1) if n not in taken]
        if not free:
            raise QuizError("Hết số trống - nhờ Ban đào tạo nới dải số.")
        number = (rng or random.SystemRandom()).choice(free)
    try:
        number = int(number)
    except (TypeError, ValueError):
        raise QuizError("Số không hợp lệ.")
    if not 1 <= number <= d["range"]:
        raise QuizError("Chọn số từ 1 đến %d." % d["range"])
    if number in taken:
        raise QuizError("Số %s đã có người giữ, chọn số khác nhé." % DR.format_number(number, d["range"]))
    repo.insert_draw_number(d["name"], ctx.user, free_slots[0], number)
    return _view(repo, d, ctx.user)


def release(ctx, repo, number):
    d = repo.lock_draw(current(repo)["name"])
    if d["status"] != C.DRAW_OPEN or repo.now() >= DR.lock_at(_dt(d["draw_at"])):
        raise QuizError("Đã khoá chọn số tuần này.")
    row = next((r for r in repo.draw_numbers(d["name"], ctx.user) if str(r["number"]) == str(number)), None)
    if not row:
        raise QuizError("Bạn không giữ số này.")
    repo.delete_draw_number(d["name"], ctx.user, row["slot"])
    return _view(repo, d, ctx.user)


def run(repo, name, rng=None, auto=False):
    """Chot ket qua (duoi khoa, mot lan). -> ket qua, hoac None neu da quay / da huy.
    auto=True (job): luot CHUA dat qua thi KHONG quay - giu mo, ve khong mat; Ban dao tao dat qua
    roi bam "Quay ngay" hoac doi gio quay."""
    d = repo.lock_draw(name)
    if not d or d["status"] != C.DRAW_OPEN:
        return None
    if auto and not d["prizes"]:
        return None
    rng = rng or random.SystemRandom()
    have = repo.week_tickets(d["week_start"])
    rows = repo.draw_numbers(name, locking=True)
    # Ve bi thu hoi sau khi chon so: chi giu so cua `have` ve dau tien.
    holders = {}
    used = {}
    for r in sorted(rows, key=lambda r: (r["user"], r["slot"])):
        if r["slot"] < have.get(r["user"], 0):
            holders[r["number"]] = r["user"]
            used.setdefault(r["user"], set()).add(r["slot"])
    needs = [(u, s) for u, n in have.items() for s in range(n) if s not in used.get(u, set())]
    for num, (u, s) in DR.assign_missing(d["range"], set(holders), needs, rng).items():
        repo.delete_draw_number(name, u, s)
        repo.insert_draw_number(name, u, s, num, auto=1)
        holders[num] = u
    results = DR.lucky_draw(d["prizes"], holders, d["range"], rng)
    repo.update_draw(name, {"status": C.DRAW_DONE, "results": results, "drawn_at": repo.now()})
    labels = {p["id"]: p["label"] for p in d["prizes"]}
    for r in results:
        if r.get("user"):
            try:
                repo.notify(r["user"], "Bạn trúng quay số tuần!",
                            "Số %s trúng %s. Liên hệ Ban đào tạo để nhận quà."
                            % (DR.format_number(r["number"], d["range"]), labels.get(r["prize"], "quà")),
                            "/%s#thuong" % C.ROUTE_LEARN, name, "dao_tao|draw|%s|%s|%s" % (name, r["user"], r["number"]),
                            reference_doctype=C.DRAW)
            except Exception:
                repo.log_error("dao_tao draw notify %s" % name)
    return results


def tick(repo=default_repo):
    """Job moi phut (hooks.py): quay cac luot toi gio. Tat: site_config ec_training_draw_disabled."""
    if repo.flag(C.DRAW_KILL_SWITCH):
        return {"skipped": True}
    done = 0
    for name in repo.due_draws(repo.now()):
        try:
            if run(repo, name, auto=True) is not None:
                done += 1
            repo.commit()
        except Exception:
            repo.rollback()
            repo.log_error("dao_tao draw tick %s" % name)
    return {"drawn": done}


# ------------------------------------------------------------------- Ban dao tao --

def admin_get(ctx, repo):
    require_host(ctx)
    d = current(repo)
    have = repo.week_tickets(d["week_start"])
    out = _view(repo, d, ctx.user)
    out.update({"holders": len(have), "total_tickets": sum(have.values()),
                "picked": len(repo.draw_numbers(d["name"])),
                "range_warning": sum(have.values()) > d["range"]})
    return out


def admin_save(ctx, repo, payload):
    require_host(ctx)
    payload = payload if isinstance(payload, dict) else {}
    d = repo.lock_draw(current(repo)["name"])
    if d["status"] != C.DRAW_OPEN:
        raise QuizError("Tuần này đã quay xong.")
    vals = {"prizes": DR.clean_prizes(payload.get("prizes") or []), "range": DR.clean_range(payload.get("range"))}
    taken = [r["number"] for r in repo.draw_numbers(d["name"])]
    if taken and max(taken) > vals["range"]:
        raise QuizError("Đã có người giữ số %d - dải số không nhỏ hơn được." % max(taken))
    if payload.get("draw_at"):
        try:
            at = _dt(str(payload["draw_at"]).replace("T", " ") + (":00" if len(str(payload["draw_at"])) == 16 else ""))
        except ValueError:
            raise QuizError("Giờ quay không hợp lệ.")
        if at <= repo.now():
            raise QuizError("Giờ quay phải ở tương lai.")
        vals["draw_at"] = at
    if payload.get("title"):
        vals["title"] = " ".join(str(payload["title"]).split())[:120]
    repo.update_draw(d["name"], vals)
    return admin_get(ctx, repo)


def draw_now(ctx, repo):
    require_host(ctx)
    d = require_found(current(repo), "lượt quay")
    if d["status"] == C.DRAW_OPEN and not d["prizes"]:
        raise QuizError("Chưa đặt quà cho tuần này - thêm quà rồi bấm Lưu trước.")
    if run(repo, d["name"]) is None:
        raise QuizError("Tuần này đã quay rồi.")
    return admin_get(ctx, repo)

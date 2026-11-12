# Copyright (c) 2026, eCentric and contributors
"""Trang Hoc (/dao-tao) + trang bai (/dao-tao/bai) cho moi nhan vien, va trang Quan ly bai hoc
(/dao-tao/quan-ly) cho Ban dao tao / HR.

Ve (tran 3 / nguoi / tuan, chung voi quiz truc tiep):
  * Quiz bai hoc dat tu 60% - 1 ve, lan dau dat (lam lai duoc, khong them ve).
  * Nop bai thuc hanh truoc han - 1 ve ngay khi nop; Ban dao tao kiem tra ngau nhien, thu hoi duoc.
Quay so tuan: CHUA lam o ban nay - luat (gio quay, so khong ai giu) cho Hoan chot.
"""
from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.application import ticket_service
from ecentric_workspace.dao_tao.application.access import require_found, require_host
from ecentric_workspace.dao_tao.domain import lesson as L, questions as Q, tickets
from ecentric_workspace.dao_tao.domain.errors import QuizError


def _card(les, prog):
    stp = L.step(les, prog)
    return {"name": les["name"], "title": les["title"], "summary": les.get("summary") or "",
            "topic": les.get("topic"), "level": les.get("level"), "tool": les.get("tool"),
            "week_start": les.get("week_start"),
            "week_label": tickets.week_label(_date(les["week_start"])) if les.get("week_start") else "",
            "has_quiz": bool(les.get("quiz")), "has_practice": bool(les.get("practice_prompt")),
            "has_video": bool(les.get("video_url")), "step": stp, "step_label": L.STEP_LABELS[stp],
            "quiz_score": (prog or {}).get("quiz_score"), "quiz_scored": (prog or {}).get("quiz_scored"),
            "url": C.lesson_url(les["name"])}


def _date(s):
    import datetime
    return datetime.date(*[int(x) for x in str(s)[:10].split("-")])


def hub(ctx, repo):
    les = repo.lessons(published_only=True)
    prog = repo.progress_of(ctx.user, [l["name"] for l in les])
    cards = [_card(l, prog.get(l["name"])) for l in les]
    ws = str(tickets.week_start(repo.now()))
    this_week = [c for c in cards if c["week_start"] == ws] or cards[:1]
    done = sum(1 for c in cards if c["step"] == L.STEP_DONE)
    return {"week": this_week, "library": cards, "done": done, "total": len(cards),
            "filters": {"topics": list(C.TOPIC_TAGS), "levels": list(C.LEVELS), "tools": list(C.TOOL_TAGS)},
            "topics": topics(ctx, repo), "tickets": ticket_service.summary(repo, ctx.user),
            "can_manage": ctx.can_host}


def lesson_detail(ctx, repo, name):
    les = require_found(repo.get_lesson(name), "bài học")
    if les["status"] != C.LESSON_PUBLISHED and not ctx.can_host:
        raise QuizError("Bài học chưa đăng.")
    prog = repo.progress_of(ctx.user, [name]).get(name) or {}
    if not prog.get("viewed_at"):
        repo.upsert_progress(name, ctx.user, {"viewed_at": repo.now()})
        prog["viewed_at"] = str(repo.now())
    quiz = None
    if les.get("quiz"):
        qz = repo.get_quiz(les["quiz"])
        if qz and qz["questions"]:
            qs = Q.require_valid(qz["questions"], rid=_stable_rid(qz["questions"]))
            quiz = {"title": qz["title"], "questions": [Q.public_view(q, None) for q in qs]}
    out = dict(les)
    out["step"] = L.step(les, prog)
    out["step_label"] = L.STEP_LABELS[out["step"]]
    out["progress"] = {k: prog.get(k) for k in ("viewed_at", "quiz_score", "quiz_scored", "quiz_at",
                                                 "practice_text", "practice_link", "practice_at", "review")}
    out["quiz"] = quiz
    out["can_manage"] = ctx.can_host
    out["practice_open"] = _practice_open(les, repo)
    return out


def _stable_rid(stored):
    """Quiz bai hoc: id phai ON DINH giua luc gui de va luc cham (nguoi hoc nop sau vai phut).
    Dung lai dung id da luu theo thu tu sinh trong clean_question."""
    ids = []
    for q in stored:
        ids.append(q.get("id") or "")
        for k in ("options", "items"):
            ids.extend(i.get("id") or "" for i in (q.get(k) or []) if q.get("type") != C.Q_TRUEFALSE)
        for p in q.get("pairs") or []:
            ids.extend([p.get("id") or "", p.get("rid") or ""])
    it = iter(ids)
    return lambda: next(it, None) or Q.default_rid()


def _practice_open(les, repo):
    due = les.get("practice_due")
    return not due or str(repo.now())[:19] <= str(due)[:19]


def submit_quiz(ctx, repo, name, answers):
    les = require_found(repo.get_lesson(name), "bài học")
    if les["status"] != C.LESSON_PUBLISHED or not les.get("quiz"):
        raise QuizError("Bài này không có quiz.")
    qz = require_found(repo.get_quiz(les["quiz"]), "quiz bài học")
    qs = Q.require_valid(qz["questions"], rid=_stable_rid(qz["questions"]))
    g = L.grade_self_quiz(qs, answers)
    prog = repo.progress_of(ctx.user, [name]).get(name) or {}
    best = max(g["score"], int(prog.get("quiz_score") or 0)) if prog.get("quiz_at") else g["score"]
    repo.upsert_progress(name, ctx.user, {"quiz_score": best, "quiz_scored": g["scored"], "quiz_at": repo.now(),
                                          "viewed_at": prog.get("viewed_at") or repo.now()})
    got = 0
    if L.passed(g["ratio"]):
        got = ticket_service.grant(repo, ctx.user, C.TICKET_LESSON_QUIZ, name, 1,
                                   "Quiz bài “%s” đạt %d/%d" % (les["title"], g["score"], g["scored"]))
    g["ticket"] = got
    g["passed"] = L.passed(g["ratio"])
    return g


def submit_practice(ctx, repo, name, text, link=""):
    les = require_found(repo.get_lesson(name), "bài học")
    if les["status"] != C.LESSON_PUBLISHED or not les.get("practice_prompt"):
        raise QuizError("Bài này không có bài thực hành.")
    text, link = L.clean_practice(text, link)
    prog = repo.progress_of(ctx.user, [name]).get(name) or {}
    if prog.get("review") == "Revoked":
        raise QuizError("Bài thực hành này đã bị Ban đào tạo thu hồi vé - liên hệ Ban đào tạo nếu cần.")
    on_time = _practice_open(les, repo)
    repo.upsert_progress(name, ctx.user, {"practice_text": text, "practice_link": link,
                                          "practice_at": repo.now(),
                                          "viewed_at": prog.get("viewed_at") or repo.now()})
    got = 0
    if on_time:
        got = ticket_service.grant(repo, ctx.user, C.TICKET_PRACTICE, name, 1,
                                   "Bài thực hành “%s”" % les["title"])
    return {"ticket": got, "on_time": on_time}


# ------------------------------------------------------------------------ binh chon --

def topics(ctx, repo):
    mine = set(repo.my_votes(ctx.user))
    rows = repo.topics()
    open_mine = sum(1 for t in rows if t["name"] in mine and t["status"] not in C.TOPIC_RELEASED)
    names = repo.full_names([t["proposed_by"] for t in rows])
    return {"items": [{"name": t["name"], "title": t["title"], "description": t["description"] or "",
                       "status": t["status"], "votes": int(t["votes"] or 0), "voted": t["name"] in mine,
                       "lesson": t["lesson"], "by": names.get(t["proposed_by"], "")}
                      for t in rows if t["status"] != C.TOPIC_REJECTED or t["name"] in mine],
            "left": L.votes_left(open_mine), "per_user": C.VOTES_PER_USER}


def propose_topic(ctx, repo, payload):
    t = L.clean_topic(payload)
    name = repo.insert_topic(dict(t, status=C.TOPIC_OPEN, votes=0, proposed_by=ctx.user))
    return {"name": name, "topics": topics(ctx, repo)}


def vote(ctx, repo, topic, on=True):
    repo.lock_user_votes(ctx.user)
    t = require_found(repo.get_topic(topic), "chủ đề")
    if t["status"] != C.TOPIC_OPEN:
        raise QuizError("Chủ đề này không còn mở bình chọn.")
    mine = repo.my_votes(ctx.user)
    if on:
        if topic in mine:
            return topics(ctx, repo)
        open_mine = sum(1 for n in mine if (repo.get_topic(n) or {}).get("status") not in C.TOPIC_RELEASED)
        if L.votes_left(open_mine) <= 0:
            raise QuizError("Bạn đã dùng hết %d phiếu. Bỏ bớt một phiếu để bầu chủ đề này." % C.VOTES_PER_USER)
        try:
            repo.add_vote(topic, ctx.user)
        except Exception as e:
            if not repo.is_duplicate(e):
                raise
    else:
        repo.remove_vote(topic, ctx.user)
    repo.recount_votes(topic)
    return topics(ctx, repo)


# ------------------------------------------------------------------- quan ly bai hoc --

def admin_list(ctx, repo):
    require_host(ctx)
    stats = repo.lesson_stats()
    rows = repo.lessons(published_only=False)
    for r in rows:
        r.update(stats.get(r["name"], {"viewed": 0, "quiz": 0, "practice": 0}))
    quizzes = [{"name": q["name"], "title": q["title"]} for q in repo.list_quizzes()]
    t = repo.topics()
    return {"lessons": rows, "quizzes": quizzes, "topics": t,
            "options": {"topics": list(C.TOPIC_TAGS), "levels": list(C.LEVELS), "tools": list(C.TOOL_TAGS),
                        "topic_statuses": list(C.TOPIC_STATUSES)}}


def admin_get(ctx, repo, name):
    require_host(ctx)
    return require_found(repo.get_lesson(name), "bài học")


def admin_save(ctx, repo, payload):
    require_host(ctx)
    payload = payload if isinstance(payload, dict) else {}
    fields = L.clean_lesson(payload)
    if fields["quiz"] and not repo.get_quiz(fields["quiz"]):
        raise QuizError("Không tìm thấy bộ quiz đã chọn.")
    status = payload.get("status") if payload.get("status") in C.LESSON_STATUSES else C.LESSON_DRAFT
    fields["status"] = status
    name = payload.get("name")
    if name:
        cur = require_found(repo.get_lesson(name), "bài học")
        if status == C.LESSON_PUBLISHED and not cur.get("published_at"):
            fields["published_at"] = repo.now()
        repo.save_lesson(name, fields)
    else:
        if status == C.LESSON_PUBLISHED:
            fields["published_at"] = repo.now()
        name = repo.insert_lesson(fields)
    return repo.get_lesson(name)


def admin_submissions(ctx, repo, name):
    require_host(ctx)
    les = require_found(repo.get_lesson(name), "bài học")
    rows = repo.progress_for_lesson(name)
    names = repo.full_names([r["user"] for r in rows])
    return {"lesson": {"name": les["name"], "title": les["title"]},
            "rows": [dict(r, full_name=names.get(r["user"], r["user"])) for r in rows]}


def admin_review(ctx, repo, name, user, verdict):
    """verdict OK | Revoked. Thu hoi = huy ve bai thuc hanh (khong dung vao ve khac)."""
    require_host(ctx)
    require_found(repo.get_lesson(name), "bài học")
    prog = repo.progress_of(user, [name]).get(name)
    if not prog or not prog.get("practice_at"):
        raise QuizError("Người này chưa nộp bài thực hành.")
    if verdict not in ("OK", "Revoked"):
        raise QuizError("Kết quả kiểm tra không hợp lệ.")
    repo.upsert_progress(name, user, {"review": verdict, "reviewed_by": ctx.user})
    revoked = repo.revoke_ticket(C.TICKET_PRACTICE, name, user, ctx.user) if verdict == "Revoked" else False
    return {"user": user, "review": verdict, "ticket_revoked": revoked}


def admin_topic(ctx, repo, topic, status, lesson=None):
    require_host(ctx)
    require_found(repo.get_topic(topic), "chủ đề")
    if status not in C.TOPIC_STATUSES:
        raise QuizError("Trạng thái không hợp lệ.")
    vals = {"status": status}
    if lesson:
        require_found(repo.get_lesson(lesson), "bài học")
        vals["lesson"] = lesson
    repo.update_topic(topic, vals)
    return {"topic": topic, "status": status}

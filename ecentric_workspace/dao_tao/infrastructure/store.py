# Copyright (c) 2026, eCentric and contributors
"""Cho DUY NHAT cua module Dao tao / Quiz duoc cham frappe.db / get_all / get_doc / cache.

Service nhan module nay qua tham so `repo` (test thay bang repository gia trong bo nho -
tests/test_services.py). Ham tra dict thuong, JSON da giai ma; khong tra Document ra ngoai.
"""
import hashlib
import json
import time

import frappe
from frappe.utils import now_datetime

from ecentric_workspace.dao_tao import constants as C


def _j(v, default):
    if not v:
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


def _d(v):
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def uhash(user):
    return hashlib.sha1((user or "").lower().encode("utf-8")).hexdigest()[:12]


def now():
    return now_datetime()


def now_ms():
    return int(time.time() * 1000)


def commit():
    frappe.db.commit()


def secret():
    """Bi mat cua site (khong bao gio gui xuong trinh duyet) - lam khoa HMAC cho hat giong xao."""
    conf = frappe.local.conf or {}
    return conf.get("encryption_key") or conf.get("secret") or frappe.local.site


# ------------------------------------------------------------------------------- quiz --

def _quiz(d):
    return {"name": d["name"], "title": d.get("title") or "", "description": d.get("description") or "",
            "status": d.get("status") or C.QUIZ_DRAFT, "template": d.get("template") or "",
            "owner": d.get("owner"), "modified": str(d.get("modified") or ""),
            "last_played": str(d.get("last_played") or ""),
            "questions": _j(d.get("questions_json"), []), "settings": _j(d.get("settings_json"), {}),
            "prizes": _j(d.get("prizes_json"), None)}


def get_quiz(name):
    if not name or not frappe.db.exists(C.QUIZ, name):
        return None
    return _quiz(frappe.get_doc(C.QUIZ, name).as_dict())


def list_quizzes(limit=200):
    rows = frappe.get_all(C.QUIZ, filters={"status": ["!=", C.QUIZ_ARCHIVED]},
                          fields=["name", "title", "status", "n_questions", "modified", "owner",
                                  "last_played", "template"],
                          order_by="modified desc", limit_page_length=limit)
    return [dict(r, modified=str(r.modified), last_played=str(r.last_played or "")) for r in rows]


def _quiz_fields(f):
    out = {k: f[k] for k in ("title", "description", "status", "template") if k in f}
    if "questions" in f:
        out["questions_json"] = _d(f["questions"])
        out["n_questions"] = len(f["questions"])
    if "settings" in f:
        out["settings_json"] = _d(f["settings"])
    if "prizes" in f:
        out["prizes_json"] = _d(f["prizes"])
    return out


def insert_quiz(fields):
    doc = frappe.get_doc(dict(_quiz_fields(fields), doctype=C.QUIZ))
    doc.insert(ignore_permissions=True)
    return doc.name


def save_quiz(name, fields):
    doc = frappe.get_doc(C.QUIZ, name)
    doc.update(_quiz_fields(fields))
    doc.save(ignore_permissions=True)
    return str(doc.modified)


def touch_quiz_played(name):
    frappe.db.set_value(C.QUIZ, name, "last_played", now_datetime(), update_modified=False)


# ---------------------------------------------------------------------------- ho so --

def get_profile(user):
    r = frappe.db.get_value(C.PROFILE, user, ["nickname", "avatar_json"], as_dict=True)
    return {"nickname": r.nickname, "avatar": _j(r.avatar_json, {})} if r else None


def save_profile(user, nickname, avatar):
    vals = {"nickname": nickname, "avatar_json": _d(avatar)}
    if frappe.db.exists(C.PROFILE, user):
        frappe.db.set_value(C.PROFILE, user, vals)
    else:
        frappe.get_doc(dict(vals, doctype=C.PROFILE, user=user)).insert(ignore_permissions=True)


# ----------------------------------------------------------------------------- phong --

_SESSION_FIELDS = ["name", "quiz", "title", "code", "host", "phase", "q_index", "version",
                   "opened_ms", "deadline_ms", "started_at", "ended_at", "snapshot_json",
                   "settings_json", "prizes_json", "state_json", "results_json", "creation"]


def _session(r):
    return {"name": r["name"], "quiz": r["quiz"], "title": r.get("title") or "", "code": r.get("code"),
            "host": r.get("host"), "phase": r.get("phase"), "index": int(r.get("q_index") or 0),
            "version": int(r.get("version") or 0), "opened_ms": int(r.get("opened_ms") or 0),
            "deadline_ms": int(r.get("deadline_ms") or 0), "started_at": str(r.get("started_at") or ""),
            "ended_at": str(r.get("ended_at") or ""), "created": str(r.get("creation") or ""),
            "questions": _j(r.get("snapshot_json"), []), "settings": _j(r.get("settings_json"), {}),
            "prizes": _j(r.get("prizes_json"), []), "state": _j(r.get("state_json"), {}),
            "results": _j(r.get("results_json"), None)}


def get_session(name, fresh=False):
    """Doc phong - qua Redis (khoa theo phien ban). fresh=True: doc thang DB (duoi khoa)."""
    if not name:
        return None
    key = C.CACHE_PREFIX + name
    if not fresh:
        hit = frappe.cache().get_value(key)
        if hit:
            return hit
    rows = frappe.get_all(C.SESSION, filters={"name": name}, fields=_SESSION_FIELDS, limit_page_length=1)
    if not rows:
        return None
    s = _session(rows[0])
    if not fresh:          # ban "fresh" doc trong transaction dang mo - khong nap vao Redis
        frappe.cache().set_value(key, s, expires_in_sec=C.CACHE_TTL)  # TTL ngan: chan ban cu ket lai
    return s


def session_by_code(code):
    rows = frappe.get_all(C.SESSION, filters={"code": code, "phase": ["in", list(C.LIVE_PHASES)]},
                          fields=["name"], order_by="creation desc", limit_page_length=1)
    return get_session(rows[0].name) if rows else None


def live_codes():
    return {r.code for r in frappe.get_all(C.SESSION, filters={"phase": ["in", list(C.LIVE_PHASES)]},
                                           fields=["code"], limit_page_length=5000)}


def live_sessions(since):
    return [dict(r, created=str(r.creation)) for r in frappe.get_all(
        C.SESSION, filters={"phase": ["in", list(C.LIVE_PHASES)], "creation": [">=", since]},
        fields=["name", "title", "code", "host", "phase", "creation"], order_by="creation desc",
        limit_page_length=50)]


def recent_sessions(limit=30):
    return [dict(r, created=str(r.creation), ended_at=str(r.ended_at or "")) for r in frappe.get_all(
        C.SESSION, fields=["name", "title", "code", "host", "phase", "quiz", "creation", "ended_at"],
        order_by="creation desc", limit_page_length=limit)]


def insert_session(fields):
    vals = dict(fields)
    for k in ("questions", "settings", "prizes", "state"):
        if k in vals:
            vals[{"questions": "snapshot_json"}.get(k, k + "_json")] = _d(vals.pop(k))
    doc = frappe.get_doc(dict(vals, doctype=C.SESSION))
    doc.insert(ignore_permissions=True)
    return doc.name


def lock_session(name):
    """Khoa dong phong (toi het transaction) VA tra ban MOI NHAT da commit (doc co khoa - khong
    dinh snapshot cu cua REPEATABLE READ). Moi thao tac doi pha / nhan cau tra loi deu qua day."""
    rows = frappe.db.sql("select %s from `tabEC Quiz Session` where name=%%s for update"
                         % ", ".join("`%s`" % f for f in _SESSION_FIELDS), (name,), as_dict=True)
    return _session(rows[0]) if rows else None


def update_session(name, values):
    """Ghi + tang phien ban + lam moi Redis SAU KHI commit (xoa ngay, nap lai lazily)."""
    vals = dict(values)
    for k, col in (("state", "state_json"), ("results", "results_json")):
        if k in vals:
            vals[col] = _d(vals.pop(k))
    if "index" in vals:
        vals["q_index"] = vals.pop("index")
    for k in ("opened_ms", "deadline_ms"):
        if k in vals:
            vals[k] = str(int(vals[k]))
    # Tang phien ban ngay trong SQL (khong doc-roi-ghi theo snapshot cu), roi doc lai co khoa.
    frappe.db.sql("update `tabEC Quiz Session` set version = coalesce(version, 0) + 1 where name=%s", (name,))
    vals["version"] = int(frappe.db.sql("select version from `tabEC Quiz Session` where name=%s for update",
                                        (name,))[0][0])
    frappe.db.set_value(C.SESSION, name, vals, update_modified=True)
    key = C.CACHE_PREFIX + name
    frappe.cache().delete_value(key)
    # Mot request khac co the nap ban CU vao Redis giua luc xoa va luc commit -> xoa lai sau commit.
    after = getattr(getattr(frappe.db, "after_commit", None), "add", None)
    if after:
        after(lambda: frappe.cache().delete_value(key))
    return vals["version"]


# ------------------------------------------------------------------------- nguoi choi --

_PLAYER_FIELDS = ["name", "session", "user", "nickname", "avatar_json", "department", "score",
                  "correct_count", "correct_ms", "streak", "best_streak", "answered", "first_rank",
                  "device", "kicked", "flags_json", "joined_at"]


def _player(r):
    d = dict(r)
    d["avatar"] = _j(d.pop("avatar_json", None), {})
    d["flags"] = _j(d.pop("flags_json", None), [])
    d["kicked"] = int(d.get("kicked") or 0)
    d["joined_at"] = str(d.get("joined_at") or "")
    for k in ("score", "correct_count", "correct_ms", "streak", "best_streak", "answered", "first_rank"):
        d[k] = int(d.get(k) or 0)
    return d


def player_name(session, user):
    return "%s-%s" % (session, uhash(user))


def get_player(session, user):
    rows = frappe.get_all(C.PLAYER, filters={"name": player_name(session, user)},
                          fields=_PLAYER_FIELDS, limit_page_length=1)
    return _player(rows[0]) if rows else None


def players(session, locking=False):
    rows = frappe.db.sql("select %s from `tabEC Quiz Player` where session=%%s order by joined_at asc%s"
                         % (", ".join("`%s`" % f for f in _PLAYER_FIELDS),
                            " lock in share mode" if locking else ""), (session,), as_dict=True)
    return [_player(r) for r in rows]


def played(user, limit=20):
    rows = frappe.db.sql(
        "select p.session, p.score, p.nickname, s.title, s.phase, s.ended_at, s.creation "
        "from `tabEC Quiz Player` p join `tabEC Quiz Session` s on s.name = p.session "
        "where p.user=%s and p.kicked=0 order by s.creation desc limit %s", (user, int(limit)), as_dict=True)
    return [dict(r, ended_at=str(r.ended_at or ""), creation=str(r.creation)) for r in rows]


def count_players(session):
    r = frappe.db.sql("select count(*) from `tabEC Quiz Player` where session=%s and kicked=0 "
                      "lock in share mode", (session,))
    return int(r[0][0] or 0)


def insert_player(fields):
    vals = dict(fields)
    vals["avatar_json"] = _d(vals.pop("avatar", {}))
    vals["flags_json"] = _d(vals.pop("flags", []))
    doc = frappe.get_doc(dict(vals, doctype=C.PLAYER))
    doc.name = player_name(fields["session"], fields["user"])
    doc.insert(ignore_permissions=True)     # trung khoa chinh -> DuplicateEntryError
    return doc.name


def update_player(session, user, values):
    vals = dict(values)
    if "avatar" in vals:
        vals["avatar_json"] = _d(vals.pop("avatar"))
    if "flags" in vals:
        vals["flags_json"] = _d(vals.pop("flags"))
    frappe.db.set_value(C.PLAYER, player_name(session, user), vals, update_modified=False)


# --------------------------------------------------------------------------- tra loi --

def answer_name(session, index, user):
    return "%s-%d-%s" % (session, int(index), uhash(user))


def insert_answer(fields):
    vals = dict(fields)
    vals["answer_json"] = _d(vals.pop("answer"))
    vals["received_ms"] = str(int(vals["received_ms"]))
    doc = frappe.get_doc(dict(vals, doctype=C.ANSWER))
    doc.name = answer_name(fields["session"], fields["q_index"], fields["user"])
    doc.insert(ignore_permissions=True)     # tra loi lan 2 -> DuplicateEntryError
    return doc.name


def answers(session, index=None, locking=False):
    """locking=True: doc co khoa (thay ca cau tra loi vua commit) - dung khi cong diem luc khoa cau."""
    sql = ("select name, user, q_index, qid, answer_json, elapsed_ms, ratio, correct, points, streak, "
           "applied from `tabEC Quiz Answer` where session=%s")
    args = [session]
    if index is not None:
        sql += " and q_index=%s"
        args.append(int(index))
    sql += " order by q_index asc" + (" lock in share mode" if locking else "")
    rows = frappe.db.sql(sql, tuple(args), as_dict=True)
    out = []
    for r in rows:
        d = dict(r)
        d["answer"] = _j(d.pop("answer_json"), {})
        d["ratio"] = None if d.get("ratio") is None else float(d["ratio"])
        out.append(d)
    return out


def count_answers(session, index):
    r = frappe.db.sql("select count(*) from `tabEC Quiz Answer` where session=%s and q_index=%s "
                      "lock in share mode", (session, int(index)))
    return int(r[0][0] or 0)


def count_active_answers(session, index):
    """So cau tra loi cua nguoi CON trong phong (khong tinh nguoi da bi moi ra)."""
    r = frappe.db.sql("select count(*) from `tabEC Quiz Answer` a join `tabEC Quiz Player` p "
                      "on p.session = a.session and p.user = a.user "
                      "where a.session=%s and a.q_index=%s and p.kicked=0 lock in share mode",
                      (session, int(index)))
    return int(r[0][0] or 0)


def get_answer(session, index, user):
    rows = frappe.db.sql("select answer_json, elapsed_ms, ratio, correct, points, streak, applied "
                         "from `tabEC Quiz Answer` where name=%s", (answer_name(session, index, user),),
                         as_dict=True)
    if not rows:
        return None
    d = dict(rows[0])
    d["answer"] = _j(d.pop("answer_json"), {})
    return d


def mark_answers_applied(session, index):
    frappe.db.sql("update `tabEC Quiz Answer` set applied=1 where session=%s and q_index=%s",
                  (session, int(index)))


def is_duplicate(exc):
    return isinstance(exc, frappe.DuplicateEntryError) or (
        isinstance(exc, frappe.UniqueValidationError) if hasattr(frappe, "UniqueValidationError") else False)


# -------------------------------------------------------------------------- nhan su --

def employee(user):
    r = frappe.db.get_value(C.EMPLOYEE, {"user_id": user, "status": "Active"},
                            ["employee_name", "department"], as_dict=True)
    if not r:
        return {"employee_name": frappe.db.get_value("User", user, "full_name") or user, "department": ""}
    dept = r.department or ""
    if dept:
        dept = frappe.db.get_value(C.DEPARTMENT, dept, "department_name") or dept
    return {"employee_name": r.employee_name, "department": dept}


def full_names(users):
    users = [u for u in set(users or []) if u]
    if not users:
        return {}
    return {r.name: r.full_name or r.name for r in frappe.get_all(
        "User", filters={"name": ["in", users]}, fields=["name", "full_name"], limit_page_length=len(users))}


# ------------------------------------------------------------------------------- ve --

def ticket_name(source, ref, user):
    return "%s-%s-%s" % (source, ref, uhash(user))


def tickets_in_week(user, week_start):
    r = frappe.db.sql("select coalesce(sum(`count`),0) from `tabEC Training Ticket` "
                      "where user=%s and week_start=%s and revoked=0", (user, week_start))
    return int(r[0][0] or 0)


def ticket_exists(source, ref, user):
    return bool(frappe.db.exists(C.TICKET, ticket_name(source, ref, user)))


def insert_ticket(fields):
    doc = frappe.get_doc(dict(fields, doctype=C.TICKET))
    doc.name = ticket_name(fields["source"], fields["ref"], fields["user"])
    doc.insert(ignore_permissions=True)
    return doc.name


def tickets_of(user, limit=30):
    return [dict(r, week_start=str(r.week_start), creation=str(r.creation)) for r in frappe.get_all(
        C.TICKET, filters={"user": user}, fields=["name", "week_start", "source", "ref", "label", "count",
                                                  "revoked", "creation"],
        order_by="creation desc", limit_page_length=limit)]


def revoke_ticket(source, ref, user, by):
    name = ticket_name(source, ref, user)
    if frappe.db.exists(C.TICKET, name):
        frappe.db.set_value(C.TICKET, name, {"revoked": 1, "revoked_by": by})
        return True
    return False


# ---------------------------------------------------------------------------- bai hoc --

_LESSON_FIELDS = ["name", "title", "status", "week_start", "summary", "topic", "level", "tool",
                  "video_url", "slide_url", "quiz", "practice_prompt", "practice_due", "published_at",
                  "modified"]


def _lesson(r, body=None):
    d = dict(r)
    for k in ("week_start", "practice_due", "published_at", "modified"):
        d[k] = str(d.get(k) or "") or None
    if body is not None:
        d["body"] = body
    return d


def lessons(published_only=True, limit=300):
    flt = {"status": C.LESSON_PUBLISHED} if published_only else {}
    return [_lesson(r) for r in frappe.get_all(C.LESSON, filters=flt, fields=_LESSON_FIELDS,
                                               order_by="week_start desc, creation desc",
                                               limit_page_length=limit)]


def get_lesson(name):
    rows = frappe.get_all(C.LESSON, filters={"name": name}, fields=_LESSON_FIELDS + ["body"],
                          limit_page_length=1)
    if not rows:
        return None
    r = dict(rows[0])
    return _lesson(r, r.pop("body", "") or "")


def insert_lesson(fields):
    doc = frappe.get_doc(dict(fields, doctype=C.LESSON))
    doc.insert(ignore_permissions=True)
    return doc.name


def save_lesson(name, fields):
    doc = frappe.get_doc(C.LESSON, name)
    doc.update(fields)
    doc.save(ignore_permissions=True)


def progress_name(lesson, user):
    return "%s-%s" % (lesson, uhash(user))


_PROGRESS_FIELDS = ["name", "lesson", "user", "viewed_at", "quiz_score", "quiz_scored", "quiz_at",
                    "practice_text", "practice_link", "practice_at", "review", "reviewed_by"]


def _progress(r):
    d = dict(r)
    for k in ("viewed_at", "quiz_at", "practice_at"):
        d[k] = str(d.get(k) or "") or None
    if not d.get("quiz_at"):
        d["quiz_score"] = None
    return d


def progress_of(user, lesson_names=None):
    flt = {"user": user}
    if lesson_names is not None:
        flt["lesson"] = ["in", list(lesson_names) or [""]]
    return {r.lesson: _progress(r) for r in frappe.get_all(C.PROGRESS, filters=flt,
                                                           fields=_PROGRESS_FIELDS, limit_page_length=1000)}


def progress_for_lesson(lesson):
    return [_progress(r) for r in frappe.get_all(C.PROGRESS, filters={"lesson": lesson},
                                                 fields=_PROGRESS_FIELDS, order_by="practice_at desc",
                                                 limit_page_length=2000)]


def upsert_progress(lesson, user, values):
    name = progress_name(lesson, user)
    if frappe.db.exists(C.PROGRESS, name):
        frappe.db.set_value(C.PROGRESS, name, values)
    else:
        doc = frappe.get_doc(dict(values, doctype=C.PROGRESS, lesson=lesson, user=user))
        doc.name = name
        doc.insert(ignore_permissions=True)


def lesson_stats():
    """{lesson: {viewed, quiz, practice}} cho trang quan ly."""
    rows = frappe.db.sql("select lesson, count(viewed_at), count(quiz_at), count(practice_at) "
                         "from `tabEC Training Progress` group by lesson")
    return {r[0]: {"viewed": r[1], "quiz": r[2], "practice": r[3]} for r in rows}


# ------------------------------------------------------------------------- binh chon --

def topics():
    return [dict(r, creation=str(r.creation)) for r in frappe.get_all(
        C.TOPIC, fields=["name", "title", "description", "status", "votes", "lesson", "proposed_by", "creation"],
        order_by="votes desc, creation asc", limit_page_length=300)]


def get_topic(name):
    r = frappe.db.get_value(C.TOPIC, name, ["name", "title", "status", "votes", "lesson"], as_dict=True)
    return dict(r) if r else None


def insert_topic(fields):
    doc = frappe.get_doc(dict(fields, doctype=C.TOPIC))
    doc.insert(ignore_permissions=True)
    return doc.name


def update_topic(name, values):
    frappe.db.set_value(C.TOPIC, name, values)


def vote_name(topic, user):
    return "%s-%s" % (topic, uhash(user))


def my_votes(user):
    """[topic] ma user dang bau."""
    return [r.topic for r in frappe.get_all(C.VOTE, filters={"user": user}, fields=["topic"],
                                             limit_page_length=500)]


def add_vote(topic, user):
    doc = frappe.get_doc({"doctype": C.VOTE, "topic": topic, "user": user})
    doc.name = vote_name(topic, user)
    doc.insert(ignore_permissions=True)


def remove_vote(topic, user):
    name = vote_name(topic, user)
    if frappe.db.exists(C.VOTE, name):
        frappe.delete_doc(C.VOTE, name, ignore_permissions=True, force=True)
        return True
    return False


def recount_votes(topic):
    n = frappe.db.count(C.VOTE, {"topic": topic})
    frappe.db.set_value(C.TOPIC, topic, "votes", n, update_modified=False)
    return n


def lock_topic(name):
    frappe.db.sql("select name from `tabEC Training Topic` where name=%s for update", (name,))


def lock_user_votes(user):
    """Khoa theo nguoi (ho so quiz lam "mutex") de 2 tab bau cung luc khong vuot 3 phieu."""
    frappe.db.sql("select name from `tabUser` where name=%s for update", (user,))


# -------------------------------------------------------------------- realtime / log --

def publish_room(session, version):
    """Bao "phong doi roi" - KHONG mang du lieu (nguoi choi tu goi state). Phat cho ca site
    (khong co room theo doc vi nguoi choi khong co quyen doc EC Quiz Session)."""
    frappe.publish_realtime(C.REALTIME_ROOM, {"s": session, "v": version}, after_commit=True)


def notify(user, title, message, url, ref, dedupe_key):
    from ecentric_workspace.notification_center.events import publish_notification_event
    return publish_notification_event(C.NOTIFY_EVENT, user, title, message, action_url=url,
                                      reference_doctype=C.SESSION, reference_name=ref,
                                      dedupe_key=dedupe_key)


def log_error(title):
    frappe.log_error(frappe.get_traceback(), title)


def read_xlsx_rows(file_url):
    """Doc tep Excel da tai len (/files/...) -> list cac dong."""
    from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file
    return read_xlsx_file_from_attached_file(file_url=file_url)


def file_owner(file_url):
    r = frappe.get_all("File", filters={"file_url": file_url}, fields=["owner"], limit_page_length=1)
    return r[0].owner if r else None

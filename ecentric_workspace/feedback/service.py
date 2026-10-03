# Copyright (c) 2026, eCentric and contributors
"""Gop y cong ty - phia NHAN VIEN: gui gop y, theo doi gop y cua minh, nhan them, "Chua on",
bang chung + "+1", tai tep. Phia nguoi xu ly o handler_service.py.

Moi ham nhan `user` do api.py / trang www lay tu PHIEN (frappe.session.user) - khong bao gio tu
HTTP. Ham nao cung kiem quyen TRUOC khi doc / ghi (repository dung ignore_permissions).

`repo` tiem vao duoc: test chay bang repo gia, khong can bench.
"""
import datetime as _dt

from ecentric_workspace.feedback import constants as C
from ecentric_workspace.feedback import domain as D


class NotFound(Exception):
    """Khong co gop y nay."""


class Forbidden(Exception):
    """Co gop y nhung nguoi nay khong duoc xem / lam viec nay - khong lo tieu de."""


class FeedbackError(Exception):
    """Loi nguoi dung gay ra - api tra success False kem thong diep."""


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.feedback import repository
    return repository


# ------------------------------------------------------------------ dung chung ---
def is_handler(repo, user):
    if not user or user == "Guest":
        return False
    return user in repo.handlers() or repo.is_admin(user)


def can_send(repo, user):
    """Nguoi gui / bam +1 duoc: nhan vien Active co tai khoan (hoac quan tri)."""
    if not user or user == "Guest":
        return False
    return bool(repo.employee(user)) or repo.is_admin(user)


def _require_sender(repo, user):
    if not can_send(repo, user):
        raise Forbidden("Chỉ nhân viên eCentric mới dùng được mục này.")


def _load(repo, name):
    fb = repo.get(name)
    if not fb:
        raise NotFound()
    return fb


def _require_own(repo, user, name):
    fb = _load(repo, name)
    if repo.sender_of(name) != user:
        raise Forbidden()
    return fb


def topic_map(repo, include_disabled=True):
    return {t["name"]: D.topic_view(t) for t in repo.topics(include_disabled=include_disabled)}


def hours_per_day(repo):
    cal = repo.calendar()
    return cal[2] if cal else 8.0


def due_from(repo, start, anonymous=False):
    """Han phan hoi = 5 ngay lam viec tu `start` (lich lam viec + ngay le cua SLA).

    An danh: lam tron len CUOI ngay lam viec do - han giu phut gui thi "Con N gio" / "Qua N gio"
    doi dung phut do, nguoi xu ly suy ra duoc gio gui."""
    cal = repo.calendar()
    if not cal:
        repo.log_message("feedback: thieu lich lam viec", "Dung han %s ngay lich" % C.FALLBACK_CALENDAR_DAYS)
        due = start + _dt.timedelta(days=C.FALLBACK_CALENDAR_DAYS)
        return due.replace(hour=18, minute=0, second=0, microsecond=0) if anonymous else due
    due = repo.business_due(start, D.sla_hours(cal[2]))
    if anonymous:
        ends = [et for _st, et in cal[0].get(due.weekday()) or []]
        if ends:
            due = _dt.datetime.combine(due.date(), max(ends))
    return due


def business_left(repo, fb, now):
    """So giay LAM VIEC con lai toi han (am = da tre bay nhieu)."""
    due = fb.get("due_at")
    if not due:
        return None
    if now <= due:
        return repo.business_seconds(now, due)
    return -repo.business_seconds(due, now)


def sla(repo, fb, now):
    return D.sla_state(fb, now, business_left(repo, fb, now), hours_per_day(repo))


def attachments_view(fb):
    """Tep dinh kem cho trang: ten + thu tu, KHONG co file_url."""
    return [{"idx": i, "file_name": a.get("file_name") or "tep"} for i, a in enumerate(fb.get("attachments") or [])]


def _clip(text):
    return D.clean_text(text, C.MESSAGE_MAX + 1)


def _check_message(text, required=False):
    if required and not text:
        raise FeedbackError("Chưa có nội dung.")
    if len(text) > C.MESSAGE_MAX:
        raise FeedbackError("Lời nhắn dài quá {0} ký tự.".format(C.MESSAGE_MAX))


# ------------------------------------------------------------------ gui ----------
def form_context(user, repo=None):
    repo = _repo(repo)
    topics = [D.topic_view(t) for t in repo.topics()]
    sent = repo.sent_today(user, repo.today())
    dept = ((repo.employee(user) or {}).get("department") or "").replace(" - EC", "")
    me = repo.full_names([user]).get(user) or user
    return {"topics": topics, "me_label": me + (" · " + dept if dept else ""), "kinds": list(C.KINDS), "remaining": max(0, C.DAILY_LIMIT - sent),
            "daily_limit": C.DAILY_LIMIT, "sla_days": C.SLA_DAYS, "can_send": can_send(repo, user)}


def submit(user, data, files=None, repo=None):
    """Gui mot gop y. files = [{name, content (bytes), size}]. -> {name, url}."""
    repo = _repo(repo)
    _require_sender(repo, user)
    topics = {t["name"]: t for t in repo.topics()}
    try:
        clean = D.normalize_submission(data or {}, topics, repo.sent_today(user, repo.today()))
    except D.Invalid as e:
        raise FeedbackError("\n".join(e.errors))
    anon = bool(clean["is_anonymous"])
    errs = D.check_files(files or [], anonymous=anon)
    if errs:
        raise FeedbackError("\n".join(errs))
    if anon:
        files = _anonymize_files(repo, files or [])
    now = repo.now()
    values = dict(clean, status=C.ST_NEW, due_at=due_from(repo, now, anon), last_activity_at=now, reopen_count=0,
                  vote_count=0)
    if anon:
        values.update(notify_pending=1, pending_event=C.PENDING_NEW)
    else:
        emp = repo.employee(user) or {}
        values["submitter"] = user
        values["submitter_department"] = emp.get("department")
    name = repo.insert_feedback(values, user, repo.today(), files or [])
    if not anon:
        repo.enqueue("ecentric_workspace.feedback.notify.new_feedback", name=name)
    return {"name": name, "url": "%s/%s" % (C.ROUTE, name)}


def _anonymize_files(repo, files):
    """Gop y an danh: doi ten tep (anh-1.png...) + ve lai anh de bo metadata (ten may, GPS, tac gia)."""
    out = []
    for i, f in enumerate(files):
        ext = D.file_ext(f["name"])
        try:
            content = repo.clean_image(f["content"], ext)
        except ValueError:
            raise FeedbackError("Ảnh không đọc được: {0}".format(f["name"]))
        out.append({"name": D.anon_file_name(i, f["name"]), "content": content, "size": len(content)})
    return out


def _tell_handlers(repo, fb, kind):
    """Bao nguoi xu ly nguoi gui vua nhan them / mo lai. An danh: de job nhac moi gio gom lai."""
    name = fb["name"]
    if fb.get("is_anonymous"):
        pending = fb.get("pending_event") if fb.get("notify_pending") else None
        repo.set_fields(name, {"notify_pending": 1, "pending_event": pending or kind})
        return
    repo.enqueue("ecentric_workspace.feedback.notify.sender_wrote", name=name, kind=kind)


# ------------------------------------------------------------------ cua toi -------
def my_cards(user, repo=None, limit=0):
    repo = _repo(repo)
    names = repo.my_names(user, limit)
    if not names:
        return []
    rows = {r["name"]: r for r in repo.list_rows({"name": ["in", names]})}
    unread = repo.my_unread(user)
    tmap = topic_map(repo)
    out = []
    for n in names:
        r = rows.get(n)
        if not r:
            continue
        steps = D.steps(r)
        out.append({"name": n, "title": r["title"], "status": r["status"],
                    "status_css": C.STATUS_CSS.get(r["status"], "new"),
                    "topic": (tmap.get(r["topic"]) or {}).get("label") or r["topic"], "anonymous": r["is_anonymous"],
                    "unread": unread.get(n, 0), "done_steps": sum(1 for s in steps if s["done"]),
                    "total_steps": len(steps), "date": D.fmt_date(r["creation"]),
                    "due": D.fmt_date(r["due_at"]) if r["status"] in (C.ST_NEW, C.ST_VIEWING) and not r.get(
                        "responded_at") else ""})
    return out


def detail(user, name, repo=None):
    """Trang /gop-y/<ma> cho NGUOI GUI: luong trao doi (khong co ghi chu noi bo)."""
    repo = _repo(repo)
    fb = _require_own(repo, user, name)
    anon = bool(fb.get("is_anonymous"))
    msgs = [m for m in repo.messages(name) if m["kind"] != C.MSG_NOTE]
    names = repo.full_names([m["author"] for m in msgs if m["author_role"] == C.ROLE_HANDLER])
    thread = []
    for m in msgs:
        mine = m["author_role"] == C.ROLE_SENDER
        thread.append({"kind": m["kind"], "mine": mine, "body": m["body"] or "",
                       "who": ("Bạn" if mine else names.get(m["author"]) or "Người xử lý"),
                       "when": D.fmt_time(m["creation"], anonymous=anon and mine),
                       "to_status": m.get("to_status") or "", "to_status_css": C.STATUS_CSS.get(m.get("to_status"), "new"),
                       "to_topic": m.get("to_topic") or ""})
    tmap = topic_map(repo)
    now = repo.now()
    st = fb["status"]
    return {"fb": {"name": name, "title": fb["title"], "body": fb["body"], "status": st,
                   "status_css": C.STATUS_CSS.get(st, "new"), "kind": fb["kind"],
                   "topic": (tmap.get(fb["topic"]) or {}).get("label") or fb["topic"], "anonymous": anon,
                   "sent": D.fmt_date_full(fb["creation"]), "due": D.fmt_date_full(fb.get("due_at")),
                   "first_response": D.fmt_date_full(fb.get("first_response_at")),
                   "on_time": bool(fb.get("first_response_at") and fb.get("due_at")
                                   and fb["first_response_at"] <= fb["due_at"]),
                   "handler": (repo.full_names([fb["viewed_by"]]).get(fb["viewed_by"]) if fb.get("viewed_by") else ""),
                   "is_public": bool(fb.get("is_public")), "votes": int(fb.get("vote_count") or 0),
                   "attachments": attachments_view(fb)},
            "sla": sla(repo, fb, now), "steps": D.steps(fb), "thread": thread,
            "can_message": not D.is_closed(st), "can_reopen": D.can_reopen(st, fb.get("reopen_count")),
            "closed": D.is_closed(st), "reopen_used": int(fb.get("reopen_count") or 0) >= C.REOPEN_MAX,
            "sla_days": C.SLA_DAYS}


def mark_read(user, name, repo=None):
    repo = _repo(repo)
    _require_own(repo, user, name)
    repo.clear_unread(name)
    return {"ok": True}


def send_message(user, name, text, repo=None):
    """Nguoi gui nhan them (gop y con mo). An danh: van an danh."""
    repo = _repo(repo)
    fb = _require_own(repo, user, name)
    if D.is_closed(fb["status"]):
        raise FeedbackError("Góp ý đã đóng. Bấm \"Chưa ổn\" nếu bạn muốn mở lại.")
    text = _clip(text)
    _check_message(text, required=True)
    now = repo.now()
    repo.insert_message({"feedback": name, "kind": C.MSG_REPLY, "author_role": C.ROLE_SENDER,
                         "author": None if fb["is_anonymous"] else user, "body": text})
    repo.set_fields(name, {"last_activity_at": now})
    _tell_handlers(repo, fb, C.PENDING_REPLY)
    return {"ok": True}


def reopen(user, name, text, repo=None):
    """"Chua on": mo lai gop y da dong (mot lan). Ve lai hang cho voi han 5 ngay lam viec moi."""
    repo = _repo(repo)
    fb = _require_own(repo, user, name)
    if not D.can_reopen(fb["status"], fb.get("reopen_count")):
        raise FeedbackError("Góp ý này không mở lại được nữa.")
    text = _clip(text)
    _check_message(text, required=True)
    now = repo.now()
    repo.insert_message({"feedback": name, "kind": C.MSG_REOPEN, "author_role": C.ROLE_SENDER,
                         "author": None if fb["is_anonymous"] else user, "body": text,
                         "from_status": fb["status"], "to_status": C.ST_NEW})
    repo.set_fields(name, {"status": C.ST_NEW, "due_at": due_from(repo, now, bool(fb["is_anonymous"])),
                           "responded_at": None,
                           "closed_at": None, "reopen_count": int(fb.get("reopen_count") or 0) + 1,
                           "reminded_soon_at": None, "reminded_overdue_at": None, "last_activity_at": now})
    if fb.get("home_announcement") or fb["status"] == C.ST_DONE:
        repo.withdraw(name)
    _tell_handlers(repo, fb, C.PENDING_REOPEN)
    return {"ok": True}


def download(user, name, idx, repo=None):
    """-> (ten tep, bytes). Nguoi gui hoac nguoi xu ly. Tep chon theo THU TU trong gop y - trang khong
    bao gio in file_url (duong dan co the trung tep cu cua nguoi gui o ho so khac)."""
    repo = _repo(repo)
    fb = _load(repo, name)
    if repo.sender_of(name) != user and not is_handler(repo, user):
        raise Forbidden()
    atts = fb.get("attachments") or []
    try:
        i = int(idx)
    except (TypeError, ValueError):
        raise NotFound()
    if not 0 <= i < len(atts):
        raise NotFound()
    got = repo.file_content(name, atts[i]["file_url"])
    if not got:
        raise NotFound()
    return got


# ------------------------------------------------------------------ bang chung ----
def board(user, sort="", flt="", repo=None):
    repo = _repo(repo)
    _require_sender(repo, user)
    rows = repo.board_rows()
    status = C.BOARD_FILTERS.get(flt)
    if status:
        rows = [r for r in rows if r["status"] == status]
    tmap = topic_map(repo)
    mine = repo.my_votes(user, [r["name"] for r in rows])
    cards = [D.board_card(r, tmap, mine) for r in rows]
    return {"cards": D.board_sort(cards, sort if sort in C.BOARD_SORTS else "nhieu-nhat"),
            "sort": sort if sort in C.BOARD_SORTS else "nhieu-nhat", "filter": flt if flt in C.BOARD_FILTERS else "",
            "my_vote_count": len(mine)}


def toggle_vote(user, name, repo=None):
    repo = _repo(repo)
    _require_sender(repo, user)
    fb = _load(repo, name)
    if not fb.get("is_public"):
        raise Forbidden()
    vote = repo.find_vote(name, user)
    if vote:
        repo.remove_vote(vote)
        voted = False
    else:
        try:
            repo.add_vote(name, user)
        except Exception as e:          # bam hai lan cung luc: ban ghi kia da co
            if not repo.is_duplicate(e):
                raise
        voted = True
    n = repo.count_votes(name)
    repo.set_vote_count(name, n)
    return {"voted": voted, "votes": n, "hot": n >= C.HOT_VOTES}


# ------------------------------------------------------------------ trang /gop-y --
def index_page(user, tab="gui", sort="", flt="", repo=None):
    repo = _repo(repo)
    tab = tab if tab in C.TABS else "gui"
    handler = is_handler(repo, user)
    ctx = {"tab": tab, "is_handler": handler, "unread_total": sum(repo.my_unread(user).values())}
    ctx.update(form_context(user, repo))
    if tab == "gui":
        ctx["mine"] = my_cards(user, repo, C.MY_RECENT)
    elif tab == "cua-toi":
        ctx["mine"] = my_cards(user, repo)
    else:
        ctx.update(board(user, sort, flt, repo))
    if handler:
        from ecentric_workspace.feedback import handler_service
        ctx["inbox_late"] = handler_service.late_count(repo)
    return ctx

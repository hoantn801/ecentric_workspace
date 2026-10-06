# Copyright (c) 2026, eCentric and contributors
"""Gop y cong ty - phia NGUOI XU LY (phong Management - EC, PO chot 04/10) + quan tri:
hop xu ly, doi trang thai, tra loi, ghi chu noi bo, chuyen chu de, dua len bang chung,
danh dau trung / spam, tong quan thang.

Nguoi xu ly KHONG BAO GIO thay danh tinh nguoi gui an danh: repo.sender_of() chi dung de gui
thong bao cho chinh nguoi gui (job nen), khong co ham nao o day tra no ra.
"""
import datetime as _dt
import json

from ecentric_workspace.feedback import constants as C
from ecentric_workspace.feedback import domain as D
from ecentric_workspace.feedback.service import FeedbackError, Forbidden, NotFound, _repo  # noqa: F401
from ecentric_workspace.feedback import service as S


def _require(repo, user):
    if not S.is_handler(repo, user):
        raise Forbidden("Chỉ Ban Giám đốc (phòng Management) xử lý góp ý.")


def _load(repo, name):
    fb = repo.get(name)
    if not fb:
        raise NotFound()
    return fb


# ------------------------------------------------------------------ hop xu ly ----
def _bucket(row, state):
    if D.is_closed(row["status"]):
        return "da-dong"
    return {"late": "qua-han", "soon": "sap-het-han"}.get(state["key"], "can-xu-ly")


def _rows(repo, now):
    rows = repo.list_rows()          # spam = "Khong lam" -> nam o "Da dong" / "Tat ca", go lai duoc
    out = []
    for r in rows:
        state = S.sla(repo, r, now) if not D.is_closed(r["status"]) else {"key": "done", "short": "", "label": ""}
        out.append((r, state))
    return out


def late_count(repo, now=None):
    now = now or repo.now()
    return sum(1 for r, st in _rows(repo, now) if st["key"] == "late")


def inbox(user, flt="can-xu-ly", topic="", q="", sel="", repo=None):
    repo = _repo(repo)
    _require(repo, user)
    now = repo.now()
    flt = flt if flt in C.INBOX_FILTERS else "can-xu-ly"
    rows = _rows(repo, now)
    tmap = S.topic_map(repo)
    counts = {k: 0 for k in C.INBOX_FILTERS}
    tcounts = {}
    picked = []
    for r, st in rows:
        b = _bucket(r, st)
        counts["tat-ca"] += 1
        if b == "da-dong":
            counts["da-dong"] += 1
        else:
            counts["can-xu-ly"] += 1            # "Can xu ly" = MOI gop y con mo
            tcounts[r["topic"]] = tcounts.get(r["topic"], 0) + 1
            if b != "can-xu-ly":
                counts[b] += 1
        if not _match(flt, b, r, topic, q):
            continue
        picked.append((r, st))
    names = repo.full_names([r["submitter"] for r, _ in picked if not r["is_anonymous"]])
    items = [_row_view(r, st, tmap, names) for r, st in picked[:C.INBOX_PAGE]]
    explicit = bool(sel and repo.exists(sel))      # nguoi xu ly BAM vao (khong phai tu chon dong dau)
    if not explicit:
        sel = items[0]["name"] if items else ""
    for i in items:
        i["on"] = i["name"] == sel
    return {"filter": flt, "topic": topic, "q": q, "counts": counts,
            "topics": [dict(t, count=tcounts.get(k, 0)) for k, t in tmap.items()
                       if t.get("enabled") or tcounts.get(k)],
            "items": items, "selected": _selected(repo, user, sel, tmap, now) if sel else None, "explicit": explicit,
            "statuses": list(C.HANDLER_STATUSES)}


def _match(flt, bucket, r, topic, q):
    if flt == "can-xu-ly" and bucket == "da-dong":
        return False
    if flt in ("qua-han", "sap-het-han", "da-dong") and bucket != flt:
        return False
    if topic and r["topic"] != topic:
        return False
    if q and q.lower() not in (r["title"] or "").lower() and q.strip().upper() != r["name"]:
        return False
    return True


def _row_view(r, st, tmap, names):
    return {"name": r["name"], "title": r["title"], "status": r["status"],
            "status_css": C.STATUS_CSS.get(r["status"], "new"), "sla_key": st["key"], "sla": st["short"],
            "topic": (tmap.get(r["topic"]) or {}).get("label") or r["topic"],
            "who": D.sender_label(r, names),
            "votes": ("%d “+1”" % int(r.get("vote_count") or 0)) if r.get("is_public") else "chưa công khai",
            "date": D.fmt_date(r["creation"]), "on": False}


def _selected(repo, user, name, tmap, now):
    fb = repo.get(name)
    if not fb:
        return None
    msgs = repo.messages(name)
    authors = repo.full_names([m["author"] for m in msgs if m["author"]] + [fb.get("submitter"), fb.get("viewed_by")])
    anon = bool(fb.get("is_anonymous"))
    sender = D.sender_label(fb, authors)
    thread = []
    for m in msgs:
        is_sender = m["author_role"] == C.ROLE_SENDER
        thread.append({"kind": m["kind"], "body": m["body"] or "", "note": m["kind"] == C.MSG_NOTE,
                       "sender": is_sender, "who": sender if is_sender else (authors.get(m["author"]) or "Hệ thống"),
                       "when": D.fmt_time(m["creation"], anonymous=anon and is_sender),
                       "to_status": m.get("to_status") or "", "to_status_css": C.STATUS_CSS.get(m.get("to_status"), "new"),
                       "from_topic": m.get("from_topic") or "", "to_topic": m.get("to_topic") or ""})
    st = S.sla(repo, fb, now)
    return {"name": name, "title": fb["title"], "body": fb["body"], "status": fb["status"],
            "status_css": C.STATUS_CSS.get(fb["status"], "new"), "kind": fb["kind"], "topic": fb["topic"],
            "topic_label": (tmap.get(fb["topic"]) or {}).get("label") or fb["topic"], "sender": sender,
            "anonymous": anon, "sent": D.fmt_time(fb["creation"], anonymous=anon), "sla": st,
            "handler": authors.get(fb.get("viewed_by")) or "", "attachments": S.attachments_view(fb),
            "is_public": bool(fb.get("is_public")), "public_title": fb.get("public_title") or fb["title"],
            "public_answer": fb.get("public_answer") or "", "votes": int(fb.get("vote_count") or 0),
            "duplicate_of": fb.get("duplicate_of") or "", "thread": thread, "reopen_count": fb.get("reopen_count") or 0}


# ------------------------------------------------------------------ thao tac ------
def mark_viewing(user, name, repo=None):
    """Nguoi xu ly mo mot gop y "Moi" -> "Dang xem" (KHONG dung dong ho han)."""
    repo = _repo(repo)
    _require(repo, user)
    fb = _load(repo, name)
    if fb["status"] != C.ST_NEW:
        return {"status": fb["status"], "changed": False}
    now = repo.now()
    repo.insert_message({"feedback": name, "kind": C.MSG_STATUS, "author_role": C.ROLE_HANDLER, "author": user,
                         "from_status": C.ST_NEW, "to_status": C.ST_VIEWING}, by=user)
    repo.set_fields(name, {"status": C.ST_VIEWING, "viewed_at": fb.get("viewed_at") or now,
                           "viewed_by": fb.get("viewed_by") or user, "last_activity_at": now}, by=user)
    _tell_sender(repo, name, C.ST_VIEWING, "", True)
    return {"status": C.ST_VIEWING, "changed": True}


def act(user, name, status="", message="", internal=False, repo=None):
    """Tra loi / doi trang thai / ghi chu noi bo. -> {status}."""
    repo = _repo(repo)
    _require(repo, user)
    fb = _load(repo, name)
    text = D.clean_text(message, C.MESSAGE_MAX + 1)
    if len(text) > C.MESSAGE_MAX:
        raise FeedbackError("Lời nhắn dài quá {0} ký tự.".format(C.MESSAGE_MAX))
    now = repo.now()
    cur = fb["status"]
    if internal:
        if not text:
            raise FeedbackError("Chưa có nội dung ghi chú.")
        repo.insert_message({"feedback": name, "kind": C.MSG_NOTE, "author_role": C.ROLE_HANDLER, "author": user,
                             "body": text}, by=user)
        repo.set_fields(name, {"last_activity_at": now}, by=user)
        return {"status": cur}
    status = status or cur
    if status == C.ST_NEW:
        status = cur
    errs = D.check_handler_status(cur, status, text) if status != cur else []
    if errs:
        raise FeedbackError("\n".join(errs))
    implicit = False
    if status == cur == C.ST_NEW and text:
        status, implicit = C.ST_VIEWING, True      # tra loi gop y "Moi" = da xem
    changed = status != cur
    if not text and not changed:
        raise FeedbackError("Chưa có gì để gửi: viết câu trả lời hoặc đổi trạng thái.")
    if text:
        repo.insert_message({"feedback": name, "kind": C.MSG_REPLY, "author_role": C.ROLE_HANDLER, "author": user,
                             "body": text}, by=user)
    values = {"last_activity_at": now}
    if changed:
        repo.insert_message({"feedback": name, "kind": C.MSG_STATUS, "author_role": C.ROLE_HANDLER, "author": user,
                             "from_status": cur, "to_status": status}, by=user)
        values["status"] = status
        values["closed_at"] = now if D.is_closed(status) else None
    if not fb.get("viewed_at"):
        values["viewed_at"] = now
    if not fb.get("viewed_by"):
        values["viewed_by"] = user
    if D.stops_clock(status if changed else None, bool(text)) and not fb.get("responded_at"):
        values["responded_at"] = now
        if not fb.get("first_response_at"):
            values["first_response_at"] = now
    repo.set_fields(name, values, by=user)
    _tell_sender(repo, name, status, text, changed and not implicit)
    _sync_popup(repo, user, dict(fb, **values))
    return {"status": status}


def set_topic(user, name, topic, repo=None):
    repo = _repo(repo)
    _require(repo, user)
    fb = _load(repo, name)
    tmap = S.topic_map(repo, include_disabled=False)
    if topic not in tmap:
        raise FeedbackError("Chủ đề không hợp lệ.")
    if topic == fb["topic"]:
        return {"topic": topic}
    old = S.topic_map(repo).get(fb["topic"]) or {}
    repo.insert_message({"feedback": name, "kind": C.MSG_TOPIC, "author_role": C.ROLE_HANDLER, "author": user,
                         "from_topic": old.get("label") or fb["topic"], "to_topic": tmap[topic]["label"]}, by=user)
    repo.set_fields(name, {"topic": topic, "last_activity_at": repo.now()}, by=user)
    return {"topic": topic}


def publish(user, name, on=True, title="", answer="", repo=None):
    """Dua len / rut khoi bang chung. Bang chung CHI hien tieu de + tra loi cong khai do nguoi xu ly
    viet lai (noi dung goc co the co chi tiet lo nguoi gui - khong bao gio hien)."""
    repo = _repo(repo)
    _require(repo, user)
    fb = _load(repo, name)
    if D.as_bool(on):
        title = D.one_line(title, C.TITLE_MAX + 1)
        answer = D.clean_text(answer, 601)
        if not title:
            raise FeedbackError("Cần tiêu đề công khai.")
        if len(title) > C.TITLE_MAX or len(answer) > 600:
            raise FeedbackError("Tiêu đề tối đa {0} ký tự, trả lời tối đa 600 ký tự.".format(C.TITLE_MAX))
        values = {"is_public": 1, "public_title": title, "public_answer": answer,
                  "public_on": fb.get("public_on") or repo.now()}
    else:
        values = {"is_public": 0}
    repo.set_fields(name, values, by=user)
    _sync_popup(repo, user, dict(fb, **values))
    return {"is_public": values["is_public"]}


def mark_duplicate(user, name, of="", spam=False, message="", repo=None):
    """Trung voi gop y khac / spam -> "Khong lam" kem ly do (nguoi gui van duoc bao)."""
    repo = _repo(repo)
    _require(repo, user)
    fb = _load(repo, name)
    of = (of or "").strip().upper()
    spam = D.as_bool(spam)
    text = D.clean_text(message, C.MESSAGE_MAX)
    values = {}
    if of:
        if of == name or not repo.exists(of):
            raise FeedbackError("Không tìm thấy góp ý gốc {0}.".format(of))
        orig = repo.get(of)
        values["duplicate_of"] = of
        if not text:
            text = ("Góp ý này trùng ý với một góp ý đã có trên bảng chung — bạn bấm “+1” ở đó để ủng hộ nhé."
                    if orig.get("is_public") else "Góp ý này trùng ý với một góp ý đang được xử lý. Cảm ơn bạn.")
    elif spam:
        values["is_spam"] = 1
        text = text or "Góp ý chưa đủ thông tin để xử lý."
    else:
        raise FeedbackError("Nhập mã góp ý gốc hoặc chọn đánh dấu spam.")
    repo.set_fields(name, values, by=user)
    return act(user, name, C.ST_DECLINED, text, repo=repo)


def _tell_sender(repo, name, status, text, changed):
    """Nguoi gui duoc bao MOI lan doi trang thai / co tra loi (PO chot 04/10). Ghi chu noi bo: khong."""
    repo.bump_unread(name)
    repo.enqueue("ecentric_workspace.feedback.notify.sender_update", name=name, status=status,
                 text=(text or "")[:200], changed=bool(changed), stamp=repo.now().isoformat())


def _sync_popup(repo, user, fb):
    """Gop y "Da lam" dang tren bang chung -> popup trang chu 7 ngay (PO chot 04/10). Khac -> rut."""
    name = fb["name"]
    if fb.get("status") == C.ST_DONE and fb.get("is_public") and fb.get("public_title"):
        today = repo.today()
        ann = repo.announce(name, C.POPUP_PREFIX + fb["public_title"], fb.get("public_answer") or "",
                            "%s?tab=bang-chung#gy-%s" % (C.ROUTE, name), today,
                            today + _dt.timedelta(days=C.POPUP_DAYS - 1))
        if ann and ann != fb.get("home_announcement"):
            repo.set_fields(name, {"home_announcement": ann}, by=user)
    elif fb.get("home_announcement"):
        repo.withdraw(name)


# ------------------------------------------------------------------ tong quan -----
def period(repo, month, now):
    """Thong ke mot thang (gop y TAO trong thang) - dung cho trang tong quan va ban tin."""
    rng = D.month_range(month)
    if not rng:
        raise FeedbackError("Tháng không hợp lệ.")
    start = _dt.datetime.combine(rng[0], _dt.time(0, 0))
    end = _dt.datetime.combine(rng[1], _dt.time(0, 0)) - _dt.timedelta(seconds=1)
    rows = repo.rows_between(start, end)
    resp = {r["name"]: repo.business_seconds(r["creation"], r["first_response_at"])
            for r in rows if r.get("first_response_at")}
    st = D.stats(rows, now, S.topic_map(repo), resp)
    per_day = S.hours_per_day(repo)
    hours = st["avg_response_hours"]
    if hours is None:
        st["avg_label"] = None
    elif hours < per_day:
        st["avg_label"] = ("%s giờ" % round(hours, 1)).replace(".", ",")
    else:
        st["avg_label"] = ("%s ngày" % round(hours / per_day, 1)).replace(".", ",")
    return st, rows


def overview(user, month="", repo=None):
    repo = _repo(repo)
    _require(repo, user)
    now = repo.now()
    today = repo.today()
    month = month if D.month_range(month) else today.strftime("%Y-%m")
    st, _rows_ = period(repo, month, now)
    prev = D.prev_month(D.month_range(month)[0])
    prev_st, _ = period(repo, prev, now)
    dg = repo.digest(month)
    hot = []
    if dg and dg.get("hot_topics"):
        try:
            hot = D.clean_hot({"topics": json.loads(dg["hot_topics"])})
        except ValueError:
            hot = []
    late = []
    tmap = S.topic_map(repo)
    for r, s in _rows(repo, now):
        if s["key"] == "late":
            late.append(r)
    names = repo.full_names([r.get("viewed_by") for r in late])
    months, d = [], today.replace(day=1)
    for _ in range(6):
        months.append(d.strftime("%Y-%m"))
        d = (d - _dt.timedelta(days=1)).replace(day=1)
    return {"month": month, "month_label": "Tháng %s/%s" % (month[5:], month[:4]), "months": months,
            "stats": st, "prev_total": prev_st["total"], "delta": st["total"] - prev_st["total"], "hot": hot,
            "hot_generated": D.fmt_time(dg.get("generated_on")) if dg else "",
            "late": [{"name": r["name"], "title": r["title"],
                      "topic": (tmap.get(r["topic"]) or {}).get("label") or r["topic"],
                      "handler": names.get(r.get("viewed_by")) or "Chưa ai nhận",
                      "sla": S.sla(repo, r, now)["short"]} for r in late],
            "ai_left": max(0, C.AI_MANUAL_DAILY_LIMIT - repo.ai_runs_today(user, today))}


def summarize_now(user, month, repo=None):
    """BGD bam "Tom tat ngay" (toi da 3 lan / ngay): AI gom chu de nong cho thang nay."""
    repo = _repo(repo)
    _require(repo, user)
    today = repo.today()
    if repo.ai_runs_today(user, today) >= C.AI_MANUAL_DAILY_LIMIT:
        raise FeedbackError("Hôm nay đã tóm tắt đủ {0} lần.".format(C.AI_MANUAL_DAILY_LIMIT))
    from ecentric_workspace.feedback import digest
    hot = digest.build(repo, month if D.month_range(month) else today.strftime("%Y-%m"), send=False)
    repo.bump_ai_runs(user, today)       # chi tinh luot khi chay xong (loi giua chung khong mat luot)
    return {"hot": hot}

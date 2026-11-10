# Copyright (c) 2026, eCentric and contributors
"""Thong bao + job nhac viec cua Trung tam Du lieu (qua notification_center - KHONG gui thang).

Ai nhan gi (PO chot 09/11/2026):
  * yeu cau moi                         -> moi nguoi team Data           (task_assigned)
  * nhan viec / doi han / tam dung / tiep tuc / doi nguoi / huy / tin nhan moi
                                        -> nguoi gui + nguoi theo doi (+ nguoi xu ly voi tin nhan)
                                                                         (mention)
  * @ten trong tin nhan                 -> nguoi duoc goi                (mention)
  * team Data bam Hoan tat              -> nguoi gui: "can nghiem thu"   (approval_required)
  * nguoi gui "Chua dat"                -> nguoi xu ly + nguoi theo doi  (mention)
  * job 09:00 ngay lam viec (gop_tin_job): sap toi han (<= 1 ngay lam viec) / qua han -> nguoi xu ly
    (task_due_soon / task_overdue - bo qua yeu cau da co task /pm vi PM tu nhac task do, va bo
    nguoi dang nghi); cho nghiem thu -> nhac nguoi gui moi ngay, du 3 ngay lam viec -> tu dong
    "Đạt (tự động)".
Nguoi thao tac khong bao gio tu nhan thong bao cua chinh minh. Moi ham nuot loi (ghi Error Log):
thong bao hong khong duoc lam hong thao tac.
"""
from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import domain as D


def url(code):
    return "%s?ma=%s" % (C.ROUTE, code)


def _names(repo, users):
    try:
        return repo.full_names(users)
    except Exception:
        return {}


def _send(repo, event, recipients, title, message, code, key, actor):
    sent = []
    for r in recipients:
        if not r or r == actor or r in sent or r in ("Guest", C.SYSTEM_USER):
            continue
        try:
            repo.notify(event, r, title, message, url(code), code, "datahub|%s|%s|%s" % (key, code, r), actor=actor)
            sent.append(r)
        except Exception:
            repo.log_error("Data Hub notify %s %s" % (event, code))
    return sent


def _followers(t):
    return [f.get("user") for f in t.get("followers") or () if f.get("user")]


def _audience(t, with_assignee=False):
    out = [t.get("requester")] + _followers(t)
    if with_assignee:
        out.append(t.get("assignee"))
    return out


def _stamp(repo):
    try:
        return repo.now().strftime("%Y%m%d%H%M%S%f")
    except Exception:
        return ""


def _title(t):
    return "%s · %s" % (t["name"], (t.get("title") or "")[:80])


def recipients_new(repo, t):
    from ecentric_workspace.data_hub import service as S
    return list(S.members(repo))


def new_request(repo, t, actor):
    try:
        who = _names(repo, [actor]).get(actor) or actor
        pri = t.get("proposed_priority") or C.PRI_NORMAL
        msg = "%s gửi yêu cầu %s (%s)." % (who, t.get("request_type") or "", pri)
        if pri == C.PRI_URGENT:
            msg += " Đề xuất Khẩn: " + (t.get("urgent_reason") or "")
        return _send(repo, C.EV_NEW, recipients_new(repo, t), "Yêu cầu dữ liệu mới: " + _title(t), msg,
                     t["name"], "new", actor)
    except Exception:
        repo.log_error("Data Hub notify new %s" % t.get("name"))
        return []


def accepted(repo, t, actor, summary):
    try:
        who = _names(repo, [actor]).get(actor) or actor
        sent = _send(repo, C.EV_UPDATE, _audience(t), "Team Data đã nhận: " + _title(t),
                     "%s nhận việc · %s" % (who, summary), t["name"], "accepted", actor)
        if not t.get("pm_task"):
            # Khong co task /pm (dong bo tat / loi) -> nguoi xu ly khong nhan "Ban duoc giao" cua PM.
            sent += _send(repo, C.EV_ASSIGNED, [t.get("assignee")], "Bạn được giao: " + _title(t), summary,
                          t["name"], "assigned|" + _stamp(repo), actor)
        return sent
    except Exception:
        repo.log_error("Data Hub notify accepted %s" % t.get("name"))
        return []


def assigned(repo, t, actor, has_task=False):
    try:
        out = []
        if not has_task:
            out += _send(repo, C.EV_ASSIGNED, [t.get("assignee")], "Bạn được giao: " + _title(t),
                         "Hạn " + D.fmt_date_full(t.get("due_date")), t["name"], "assigned|" + _stamp(repo), actor)
        names = _names(repo, [t.get("assignee")])
        out += _send(repo, C.EV_UPDATE, _audience(t), "Đổi người xử lý: " + _title(t),
                     "Người xử lý mới: " + (names.get(t.get("assignee")) or t.get("assignee") or ""),
                     t["name"], "assignee|" + _stamp(repo), actor)
        return out
    except Exception:
        repo.log_error("Data Hub notify assigned %s" % t.get("name"))
        return []


def updated(repo, t, actor, changes, note="", source=C.SRC_HUB):
    try:
        if not changes:
            return []
        msg = "; ".join(changes)
        if note:
            msg += " · " + note[:300]
        if source == C.SRC_PM:
            msg += " (từ /pm)"
        return _send(repo, C.EV_UPDATE, _audience(t), "Cập nhật: " + _title(t), msg, t["name"],
                     "update|" + _stamp(repo), actor)
    except Exception:
        repo.log_error("Data Hub notify update %s" % t.get("name"))
        return []


def review(repo, t, actor, note=""):
    try:
        msg = "Team Data đã hoàn tất. Bấm Đạt hoặc Chưa đạt (sau %d ngày làm việc tự đóng Đạt)." % (
            C.AUTO_CLOSE_WORKING_DAYS)
        if t.get("output_link"):
            msg += " Kết quả: " + t["output_link"]
        if note:
            msg += " · " + note[:300]
        out = _send(repo, C.EV_REVIEW, [t.get("requester")], "Cần nghiệm thu: " + _title(t), msg, t["name"],
                    "review|" + _stamp(repo), actor)
        out += _send(repo, C.EV_UPDATE, _followers(t), "Đã hoàn tất: " + _title(t), "Chờ người gửi nghiệm thu.",
                     t["name"], "done|" + _stamp(repo), actor)
        return out
    except Exception:
        repo.log_error("Data Hub notify review %s" % t.get("name"))
        return []


def reopened(repo, t, actor, reason, rejected=True):
    try:
        title = ("Chưa đạt, mở lại: " if rejected else "Mở lại: ") + _title(t)
        return _send(repo, C.EV_UPDATE, [t.get("assignee")] + _audience(t), title, reason or "", t["name"],
                     "reopen|" + _stamp(repo), actor)
    except Exception:
        repo.log_error("Data Hub notify reopen %s" % t.get("name"))
        return []


def closed(repo, t, actor, acceptance):
    try:
        if acceptance == C.ACC_AUTO:
            return _send(repo, C.EV_UPDATE, [t.get("requester"), t.get("assignee")], "Đã đóng: " + _title(t),
                         "Đạt (tự động) - không có phản hồi sau %d ngày làm việc." % C.AUTO_CLOSE_WORKING_DAYS,
                         t["name"], "autoclose", C.SYSTEM_USER)
        return _send(repo, C.EV_UPDATE, [t.get("assignee")] + _followers(t), "Nghiệm thu Đạt: " + _title(t), "",
                     t["name"], "closed", actor)
    except Exception:
        repo.log_error("Data Hub notify close %s" % t.get("name"))
        return []


def cancelled(repo, t, actor, reason):
    try:
        return _send(repo, C.EV_UPDATE, _audience(t, with_assignee=True), "Đã huỷ: " + _title(t), reason or "",
                     t["name"], "cancel", actor)
    except Exception:
        repo.log_error("Data Hub notify cancel %s" % t.get("name"))
        return []


def new_message(repo, t, actor, body, mentions):
    try:
        who = _names(repo, [actor]).get(actor) or actor
        snippet = (body or "(tệp đính kèm)")[:200]
        stamp = _stamp(repo)
        out = _send(repo, C.EV_MENTION, mentions, "%s nhắc bạn trong %s" % (who, t["name"]), snippet,
                    t["name"], "mention|" + stamp, actor)
        rest = [u for u in _audience(t, with_assignee=True) if u not in mentions]
        out += _send(repo, C.EV_UPDATE, rest, "Tin nhắn mới: " + _title(t), "%s: %s" % (who, snippet),
                     t["name"], "msg|" + stamp, actor)
        return out
    except Exception:
        repo.log_error("Data Hub notify message %s" % t.get("name"))
        return []


# ------------------------------------------------------------------ job 09:00 ---------------
def run_daily(repo=None, pm=None):
    """Job 09:00 (chi ngay lam viec cua cong ty): nhac han nguoi xu ly, nhac / tu dong nghiem thu.
    -> {due_soon, overdue, review_reminded, auto_closed}."""
    from ecentric_workspace.data_hub import service as S
    repo = S._repo(repo)
    today, hol = repo.today(), repo.holidays()
    out = {"due_soon": 0, "overdue": 0, "review_reminded": 0, "auto_closed": 0}
    if not D.is_working_day(today, hol):
        return out
    for t in repo.list_rows({"status": ["in", [C.ST_DOING, C.ST_REVIEW]]}, fields=None):
        try:
            if t.get("status") == C.ST_DOING:
                _remind_due(repo, t, today, hol, out)
            else:
                _review(repo, t, today, hol, out, pm)
        except Exception:
            repo.log_error("Data Hub daily %s" % t.get("name"))
    return out


def _remind_due(repo, t, today, hol, out):
    due, who = D.as_date(t.get("due_date")), t.get("assignee")
    if not due or not who or t.get("pm_task"):
        return   # co task /pm: pm_due_soon_scan / pm_overdue_scan da nhac nguoi nhan
    if repo.is_off_today(who, today):
        return
    if due < today:
        n = D.working_days_between(due, today, hol)
        if _send(repo, C.EV_OVERDUE, [who], "Quá hạn %d ngày: %s" % (n, _title(t)),
                 "Hạn " + D.fmt_date_full(due) + ". Cập nhật tiến độ hoặc dời hạn (kèm lý do).", t["name"],
                 "overdue|" + today.isoformat(), C.SYSTEM_USER):
            out["overdue"] += 1
    elif D.working_days_between(today, due, hol) <= C.DUE_SOON_DAYS:
        if _send(repo, C.EV_DUE_SOON, [who], "Sắp tới hạn %s: %s" % (D.fmt_date(due), _title(t)), "",
                 t["name"], "duesoon|" + today.isoformat(), C.SYSTEM_USER):
            out["due_soon"] += 1


def _review(repo, t, today, hol, out, pm):
    from ecentric_workspace.data_hub import ops_service as O
    done = D.as_date(t.get("done_at"))
    if not done:
        return
    if D.working_days_between(done, today, hol) >= C.AUTO_CLOSE_WORKING_DAYS:
        full = repo.lock(t["name"])
        if full and full.get("status") == C.ST_REVIEW:
            O.apply_close(repo, full, C.SYSTEM_USER, C.ACC_AUTO)
            out["auto_closed"] += 1
        return
    if done < today and _send(repo, C.EV_REVIEW, [t.get("requester")], "Nhắc nghiệm thu: " + _title(t),
                              "Bấm Đạt hoặc Chưa đạt. Không phản hồi thì tự đóng Đạt sau %d ngày làm việc." %
                              C.AUTO_CLOSE_WORKING_DAYS, t["name"], "remind_review|" + today.isoformat(),
                              C.SYSTEM_USER):
        out["review_reminded"] += 1


def _gop_tin_job(fn):
    try:
        from ecentric_workspace.notification_center.nhip_gui import gop_tin_job
        return gop_tin_job(fn)
    except Exception:
        return fn


@_gop_tin_job
def daily():
    """Scheduler: cron "0 9 * * *" (hooks.py, khu "Nhac viec 09:00"). Bao gop_tin_job: tin cung
    nguoi nhan trong dot gom thanh mot."""
    from ecentric_workspace.data_hub import repository as R
    try:
        out = run_daily(R)
        R.commit()
        return out
    except Exception:
        R.log_error("Data Hub daily job")

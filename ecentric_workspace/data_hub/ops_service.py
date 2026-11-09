# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu - phia TEAM DATA: nhan viec, doi nguoi / uu tien / ngay bat dau / han (ly do bat
buoc), tam dung - tiep tuc (dong ho han dung), hoan tat -> Cho nghiem thu.

Ham public (accept / update / pause / resume / mark_done) kiem quyen (team Data = role trong Settings,
hoac System Manager). Cac ham apply_* la BUOC GHI dung chung - goi tu day, tu service (nghiem thu,
huy), tu pm_sync (thay doi ben /pm) va tu job (tu dong) - nen moi duong ghi cung mot nhat ky, cung
mot thong bao, cung mot luat dong ho han. apply_* KHONG kiem quyen: nguoi goi da kiem.
"""
from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import domain as D
from ecentric_workspace.data_hub import service as S


def _sync():
    from ecentric_workspace.data_hub import pm_sync
    return pm_sync


def _notify():
    from ecentric_workspace.data_hub import notify
    return notify


def _set(repo, t, values):
    repo.set_fields(t["name"], values)
    t.update(values)


# ------------------------------------------------------------------ nhan viec -------------
def accept(user, code, assignee="", start_date="", due_date="", priority="", reason="", repo=None, pm=None):
    """Team Data nhan yeu cau: nguoi xu ly, ngay bat dau, han (mac dinh theo quy tac; sua thi bat buoc
    ly do), xac nhan / ha muc Khan. Tao task /pm cho nguoi xu ly. -> {status, due, pm_task, warning}."""
    repo = S._repo(repo)
    S.require_operate(repo, user)
    t = repo.lock(code)
    if not t:
        raise S.NotFound(code)
    if t.get("status") != C.ST_WAITING:
        S._fail("Yêu cầu này đã được nhận hoặc đã đóng (đang: {0}). Tải lại trang.".format(t.get("status")))
    team = S.members(repo)
    assignee = (assignee or "").strip() or (user if user in team else "")
    errs = []
    if not assignee:
        errs.append("Chọn người xử lý.")
    elif assignee not in team:
        errs.append("Người xử lý phải thuộc team Data.")
    pri = (priority or "").strip() or D.queue_priority(t)
    if pri not in C.PRIORITIES:
        errs.append("Mức ưu tiên không hợp lệ.")
    today, hol = repo.today(), repo.holidays()
    start = D.as_date(start_date) if start_date else D.default_start(today, hol)
    if not start:
        errs.append("Ngày bắt đầu không hợp lệ.")
    elif start < today:
        errs.append("Ngày bắt đầu không được trước hôm nay.")
    if errs:
        S._fail(errs)
    r = S.ticket_rules(repo, t)
    n = D.ticket_sla_days(r, t.get("request_type"), pri)
    default_due = D.due_from(start, n, hol)
    due = D.as_date(due_date) if due_date else default_due
    reason = D.clean_text(reason, C.REASON_MAX)
    errs = D.check_due_change(default_due, due, reason, start)
    if errs:
        S._fail(errs)
    proposed = t.get("proposed_priority") or C.PRI_NORMAL
    _set(repo, t, {"status": C.ST_DOING, "assignee": assignee, "priority": pri, "priority_confirmed_by": user,
                   "start_date": start, "due_date": due, "original_due_date": due, "sla_days": n,
                   "rule_version": r["version"], "accepted_at": repo.now(), "accepted_by": user})
    if pri != proposed:
        S.log(repo, code, C.EV_PRIORITY, user, from_value=proposed, to_value=pri,
              note=("Hạ mức Khẩn khi nhận việc" if proposed == C.PRI_URGENT else "Đổi mức khi nhận việc"))
    elif pri == C.PRI_URGENT:
        S.log(repo, code, C.EV_PRIORITY, user, from_value="Đề xuất " + pri, to_value=pri, note="Xác nhận Khẩn")
    names = repo.full_names([assignee])
    summary = "giao %s · bắt đầu %s · hạn %s (%d ngày làm việc%s)" % (
        names.get(assignee) or assignee, D.fmt_date(start), D.fmt_date(due), n,
        "" if due == default_due else ", hạn quy tắc " + D.fmt_date(default_due))
    S.log(repo, code, C.EV_ACCEPTED, user, from_value="", to_value=summary[:140], note=reason)
    task, warn = _sync().push_accept(repo, t, user, pm=pm)
    _notify().accepted(repo, t, user, summary)
    return {"status": C.ST_DOING, "due": due.isoformat(), "pm_task": task or "", "warning": warn or ""}


# ------------------------------------------------------------------ cap nhat ---------------
def update(user, code, data=None, repo=None, pm=None):
    """O "Cap nhat" cua team Data (popup / Dieu phoi). data = {status, priority, assignee, start_date,
    due_date, reason, note, output_link} - truong nao khong gui thi giu nguyen.
    -> {changes: [..], warnings: [..], status}."""
    repo = S._repo(repo)
    S.require_operate(repo, user)
    data = data or {}
    t = repo.lock(code)
    if not t:
        raise S.NotFound(code)
    st = t.get("status")
    if st == C.ST_WAITING:
        S._fail("Yêu cầu chưa có người nhận - bấm “Nhận việc” trước.")
    if st in C.CLOSED:
        S._fail("Yêu cầu đã đóng.")
    hol = repo.holidays()
    errs = []
    new_status = (data.get("status") or st).strip()
    if new_status not in C.STATUSES or not D.can_team_move(st, new_status):
        errs.append("Không chuyển được từ “{0}” sang “{1}”.".format(st, new_status))
    pri = (data.get("priority") or t.get("priority") or "").strip()
    if pri and pri not in C.PRIORITIES:
        errs.append("Mức ưu tiên không hợp lệ.")
    assignee = (data.get("assignee") or t.get("assignee") or "").strip()
    if assignee != t.get("assignee") and assignee not in S.members(repo):
        errs.append("Người xử lý phải thuộc team Data.")
    start = D.as_date(data.get("start_date")) if data.get("start_date") else D.as_date(t.get("start_date"))
    old_due = D.as_date(t.get("due_date"))
    due = D.as_date(data.get("due_date")) if data.get("due_date") else old_due
    reason = D.clean_text(data.get("reason"), C.REASON_MAX)
    errs += D.check_due_change(old_due, due, reason, start)
    note = D.clean_text(data.get("note"), C.MESSAGE_MAX)
    link = (data.get("output_link") or "").strip()
    if link and (len(link) > C.LINK_MAX or not D.valid_link(link)):
        errs.append("Link kết quả phải bắt đầu bằng http:// hoặc https://")
    if errs:
        S._fail(errs)
    changes, warnings = [], []
    if assignee != (t.get("assignee") or ""):
        warnings += apply_assignee(repo, t, user, assignee, pm=pm)
        changes.append("người xử lý")
    if pri and pri != (t.get("priority") or ""):
        old = t.get("priority") or ""
        _set(repo, t, {"priority": pri, "priority_confirmed_by": user})
        S.log(repo, code, C.EV_PRIORITY, user, from_value=old, to_value=pri)
        warnings += _sync().push_change(repo, t, user, ("priority",), pm=pm)
        changes.append("ưu tiên " + pri)
    if start and start != D.as_date(t.get("start_date")):
        old = t.get("start_date")
        _set(repo, t, {"start_date": start})
        S.log(repo, code, C.EV_START, user, from_value=D.iso(old), to_value=start.isoformat())
        warnings += _sync().push_change(repo, t, user, ("start",), pm=pm)
        changes.append("ngày bắt đầu " + D.fmt_date(start))
    if due != old_due:
        warnings += apply_due(repo, t, user, due, reason, pm=pm, notify_now=False)
        changes.append("hạn %s → %s" % (D.fmt_date(old_due), D.fmt_date(due)))
    if link and link != (t.get("output_link") or ""):
        _set(repo, t, {"output_link": link})
        changes.append("link kết quả")
    if note:
        # Ghi chu cho nguoi gui = mot tin trong khung trao doi (thong bao gom chung ben duoi).
        repo.insert_message({"ticket": code, "author": user, "body": note, "mentions": "[]"})
    if new_status != st:
        if new_status == C.ST_PAUSED:
            apply_pause(repo, t, user, note, notify_now=False)
            changes.append("tạm dừng – chờ người gửi")
        elif new_status == C.ST_DOING and st == C.ST_PAUSED:
            warnings += apply_resume(repo, t, user, pm=pm, notify_now=False)
            changes.append("tiếp tục, hạn " + D.fmt_date(t.get("due_date")))
        elif new_status == C.ST_DOING and st == C.ST_REVIEW:
            warnings += apply_reopen(repo, t, user, note or reason, pm=pm, by_team=True)
            changes.append("mở lại")
        elif new_status == C.ST_REVIEW:
            warnings += apply_done(repo, t, user, note=note, pm=pm)
            changes.append("hoàn tất")
    if not changes and not note:
        S._fail("Chưa có gì thay đổi.")
    if new_status != C.ST_REVIEW and (changes or note):
        # Hoan tat da bao rieng (cho nghiem thu); con lai gom MOT thong bao.
        _notify().updated(repo, t, user, changes, note or reason)
    return {"changes": changes, "warnings": [w for w in warnings if w], "status": t.get("status")}


def pause(user, code, note="", repo=None, pm=None):
    return update(user, code, {"status": C.ST_PAUSED, "note": note}, repo=repo, pm=pm)


def resume(user, code, repo=None, pm=None):
    return update(user, code, {"status": C.ST_DOING}, repo=repo, pm=pm)


def mark_done(user, code, output_link="", note="", repo=None, pm=None):
    return update(user, code, {"status": C.ST_REVIEW, "output_link": output_link, "note": note}, repo=repo, pm=pm)


# ------------------------------------------------------------------ buoc ghi dung chung -----
def apply_due(repo, t, actor, new_due, reason, source=C.SRC_HUB, pm=None, push=True, notify_now=True):
    old = D.as_date(t.get("due_date"))
    if new_due == old:
        return []
    _set(repo, t, {"due_date": new_due, "due_change_count": int(t.get("due_change_count") or 0) + 1})
    S.log(repo, t["name"], C.EV_DUE, actor, source=source, from_value=D.iso(old), to_value=D.iso(new_due),
          note=reason)
    warns = _sync().push_change(repo, t, actor, ("due",), pm=pm) if push else []
    if notify_now:
        _notify().updated(repo, t, actor, ["hạn %s → %s" % (D.fmt_date(old), D.fmt_date(new_due))], reason,
                          source=source)
    return warns


def apply_assignee(repo, t, actor, new, source=C.SRC_HUB, pm=None, push=True):
    old = t.get("assignee") or ""
    if new == old:
        return []
    _set(repo, t, {"assignee": new})
    S.log(repo, t["name"], C.EV_ASSIGNEE, actor, source=source, from_value=old, to_value=new)
    warns = _sync().push_change(repo, t, actor, ("assignee",), pm=pm, old_assignee=old) if push else []
    _notify().assigned(repo, t, actor, has_task=bool(t.get("pm_task")) and push)
    return warns


def apply_pause(repo, t, actor, note="", source=C.SRC_HUB, notify_now=True):
    _set(repo, t, {"status": C.ST_PAUSED, "paused_since": repo.now()})
    S.log(repo, t["name"], C.EV_PAUSE, actor, source=source, from_value=C.ST_DOING, to_value=C.ST_PAUSED,
          note=note)
    if notify_now:
        _notify().updated(repo, t, actor, ["tạm dừng – chờ người gửi"], note, source=source)


def apply_resume(repo, t, actor, source=C.SRC_HUB, pm=None, push=True, notify_now=True):
    """Tiep tuc: han cong them so ngay lam viec da dung (dong ho han dung khi cho nguoi gui)."""
    now, hol = repo.now(), repo.holidays()
    since = D.as_datetime(t.get("paused_since")) or now
    n = D.paused_working_days(since, now, hol)
    old_due = D.as_date(t.get("due_date"))
    new_due = D.extend_due(old_due, n, hol)
    secs = int(t.get("paused_seconds") or 0) + max(0, int((now - since).total_seconds()))
    _set(repo, t, {"status": C.ST_DOING, "paused_since": None, "paused_seconds": secs,
                   "paused_days": int(t.get("paused_days") or 0) + n, "due_date": new_due})
    S.log(repo, t["name"], C.EV_RESUME, actor, source=source, from_value=D.iso(old_due), to_value=D.iso(new_due),
          note=("Hạn cộng %d ngày làm việc tạm dừng" % n) if n else "")
    warns = _sync().push_change(repo, t, actor, ("due",), pm=pm) if (push and new_due != old_due) else []
    if notify_now:
        _notify().updated(repo, t, actor, ["tiếp tục, hạn " + D.fmt_date(new_due)], "", source=source)
    return warns


def _avail():
    from ecentric_workspace.data_hub import avail_service
    return avail_service


def apply_done(repo, t, actor, note="", source=C.SRC_HUB, pm=None, push=True):
    """Team Data xong -> Cho nghiem thu (nguoi gui bam Dat / Chua dat; 3 ngay lam viec tu dong).
    Dot 2: ke hoach bo sung data (DA-) team Data tu len (khong tu de xuat) -> Hoan tat luon, khong cho
    nghiem thu; o ma tran chuyen "Co" (avail_service.on_ticket_closed)."""
    warns = []
    if t.get("status") == C.ST_PAUSED:
        warns += apply_resume(repo, t, actor, source=source, pm=pm, push=push, notify_now=False)
    direct = t.get("kind") == C.KIND_AVAILABILITY and not _avail().needs_acceptance(repo, t)
    now = repo.now()
    values = {"status": C.ST_DONE if direct else C.ST_REVIEW, "done_at": now, "acceptance": "",
              "reminded_review_on": None}
    if direct:
        values["closed_at"] = now
    _set(repo, t, values)
    S.log(repo, t["name"], C.EV_DONE, actor, source=source, from_value=C.ST_DOING, to_value=values["status"],
          note=note)
    if push:
        warns += _sync().push_state(repo, t, actor, "Done", pm=pm)
    if direct:
        _avail().on_ticket_closed(repo, t, actor)
        _avail().da_closed_notify(repo, t, actor)
    else:
        _notify().review(repo, t, actor, note)
    return warns


def apply_reopen(repo, t, actor, reason, source=C.SRC_HUB, pm=None, push=True, by_team=False):
    """Cho nghiem thu -> Dang xu ly. Nguoi gui "Chua dat" (dem reject_count) hoac team Data mo lai."""
    values = {"status": C.ST_DOING, "done_at": None}
    if not by_team and source == C.SRC_HUB:
        values.update({"acceptance": C.ACC_FAIL, "reject_count": int(t.get("reject_count") or 0) + 1})
    _set(repo, t, values)
    ev = C.EV_ACCEPT_FAIL if "acceptance" in values else C.EV_RESUME
    S.log(repo, t["name"], ev, actor, source=source, from_value=C.ST_REVIEW, to_value=C.ST_DOING, note=reason)
    warns = _sync().push_state(repo, t, actor, "In Progress", pm=pm) if push else []
    _notify().reopened(repo, t, actor, reason, rejected="acceptance" in values)
    return warns


def apply_close(repo, t, actor, acceptance):
    """Dat (nguoi gui) / Dat (tu dong) -> Hoan tat. Task /pm da Done tu luc team Data bam Hoan tat."""
    _set(repo, t, {"status": C.ST_DONE, "acceptance": acceptance, "closed_at": repo.now()})
    ev = C.EV_AUTO_CLOSE if acceptance == C.ACC_AUTO else C.EV_ACCEPT_OK
    S.log(repo, t["name"], ev, actor if acceptance != C.ACC_AUTO else C.SYSTEM_USER,
          source=C.SRC_SYSTEM if acceptance == C.ACC_AUTO else C.SRC_HUB, from_value=C.ST_REVIEW,
          to_value=C.ST_DONE)
    _avail().on_ticket_closed(repo, t, actor)     # dot 2: DA -> o ma tran "Co"; Power BI Dat -> Thu vien
    _notify().closed(repo, t, actor, acceptance)


def apply_cancel(repo, t, actor, reason, pm=None, push=True):
    old = t.get("status")
    _set(repo, t, {"status": C.ST_CANCELLED, "cancel_reason": reason, "closed_at": repo.now(),
                   "paused_since": None})
    S.log(repo, t["name"], C.EV_CANCEL, actor, from_value=old, to_value=C.ST_CANCELLED, note=reason)
    warns = _sync().push_state(repo, t, actor, "Cancelled", pm=pm) if (push and t.get("pm_task")) else []
    _notify().cancelled(repo, t, actor, reason)
    return warns

# Copyright (c) 2026, eCentric and contributors
"""Nhac chot cong thang - di qua Notification Center (chuong + Teams + web push).

HAI MOC (Hoan chot 29/09):
    08:35 ngay 1    -> moi nguoi: han chot cong cua minh; leader: them han chot team.
    09:00 ngay chot -> chi nguoi CHUA chot / leader con team chua chot.
Moi nguoi nhan toi da MOT tin moi moc (gop phan nhan vien + phan leader), de khong
ban hai DM Teams cung luc. 08:35 chu khong 08:30 de khong trung giay voi nhac cham cong.

Hai ham rieng cho hai cron: Frappe khoa Scheduled Job Type theo dotted path, cung
mot ham o hai cron chi giu MOT (xem checkin_reminder.py).
Tat: site_config ec_timesheet_close_reminder_disabled = 1.
"""
import frappe
from frappe.utils import now_datetime

from ecentric_workspace.hr.timesheet_close import rules as R
from ecentric_workspace.hr.timesheet_close import service as S
from ecentric_workspace.notification_center.events import publish_notification_event

KILL_SWITCH = "ec_timesheet_close_reminder_disabled"
ACTION_URL = "/ec-hr/attendance#ha-close-card"
_DOW = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


def _fmt(dt):
    return "%s %s" % (_DOW[dt.weekday()], dt.strftime("%d/%m"))


def _label(period):
    return "tháng %d/%s" % (int(period[5:7]), period[:4])


def _hr_users():
    return [r[0] for r in frappe.db.sql("""
        select distinct hr.parent from `tabHas Role` hr join `tabUser` u on u.name = hr.parent
        where hr.parenttype = 'User' and hr.role in ('EC CnB', 'HR Manager') and u.enabled = 1""")]


def _plan(period, only_pending):
    """user -> {'member': bool, 'team': n_open, 'nolead': n_open}"""
    rows = frappe.get_all(S.DT, filters={"period_month": period},
                          fields=["user", "status", "lead_user"])
    plan = {}

    def slot(u):
        return plan.setdefault(u, {"member": False, "team": 0, "nolead": 0})

    nolead_open = 0
    for r in rows:
        if r.user and (not only_pending or r.status == R.ST_OPEN):
            slot(r.user)["member"] = True
        if r.status != R.ST_CLOSED:
            if r.lead_user:
                slot(r.lead_user)["team"] += 1
            else:
                nolead_open += 1
        elif not only_pending and r.lead_user:
            slot(r.lead_user)
    if nolead_open:
        for u in _hr_users():
            slot(u)["nolead"] = nolead_open
    return plan


def _send(kind, period, m_due, l_due, only_pending):
    if frappe.conf.get(KILL_SWITCH):
        return {"skipped": "kill switch"}
    sent = 0
    for user, p in _plan(period, only_pending).items():
        parts = []
        if p["member"]:
            parts.append("Bấm Chốt công %s trước 12:00 %s. Gửi giải trình ngày thiếu công / đi muộn "
                         "TRƯỚC khi chốt — chốt rồi không sửa được nữa." % (_label(period), _fmt(m_due)))
        if p["team"]:
            parts.append("Chốt công cho team (%d người) trước 15:00 %s — duyệt hết giải trình và đơn "
                         "nghỉ đang chờ trước." % (p["team"], _fmt(l_due)))
        if p["nolead"]:
            parts.append("CnB/HR chốt thay %d người không có quản lý trực tiếp trước 15:00 %s."
                         % (p["nolead"], _fmt(l_due)))
        if not parts:
            continue
        title = ("Nhắc: hôm nay chốt công %s" if kind == "due" else "Chốt công %s: hạn %s") % (
            _label(period), _fmt(m_due))
        try:
            publish_notification_event(
                "task_assigned", user, title, " ".join(parts), severity="action_required",
                action_url=ACTION_URL, reference_doctype=S.DT,
                dedupe_key="tsclose|%s|%s|%s" % (kind, period, user), from_user="Administrator")
            sent += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "timesheet_close reminder " + str(user))
    return {"sent": sent, "period": period}


def remind_day1():
    """Cron 35 8 * * * - chi lam viec vao ngay 1."""
    now = now_datetime()
    if now.day != 1:
        return None
    period = R.prev_period(now)
    if not R.applies(period):
        return None
    S.ensure_rows(period)
    m_due, l_due = S.deadlines(period)
    return _send("day1", period, m_due, l_due, only_pending=False)


def remind_close_day():
    """Cron 0 9 * * * - chi lam viec vao dung ngay chot."""
    now = now_datetime()
    period = R.prev_period(now)
    if not R.applies(period):
        return None
    m_due, l_due = S.deadlines(period)
    if now.date() != m_due.date():
        return None
    return _send("due", period, m_due, l_due, only_pending=True)


def preview(kind="day1"):
    """bench execute ...reminders.preview : xem ai se nhan, KHONG gui."""
    now = now_datetime()
    period = R.prev_period(now)
    return {"period": period, "deadlines": [str(x) for x in S.deadlines(period)],
            "plan": _plan(period, only_pending=(kind == "due"))}

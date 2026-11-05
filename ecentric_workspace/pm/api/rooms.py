# Copyright (c) 2026, eCentric and contributors
"""Phòng họp (05/11/2026) - xem lịch trống/bận và đặt phòng, đồng bộ hai chiều với Teams.

Source of truth = Exchange: each EC Meeting Room is a Microsoft 365 room mailbox.
  * READ  : the room's own calendar (Graph calendarView on the room mailbox, one $batch for all
            rooms). Anything booked from Teams/Outlook shows here as "busy" automatically.
  * WRITE : book() creates a normal Outlook/Teams event on the CALLER'S calendar with the room
            invited as a resource (+ Teams link). The room mailbox auto-accepts when free and
            auto-declines a clash (Set-CalendarProcessing AutoAccept, AllowConflicts off), exactly
            like booking from Teams. cancel() = Graph cancel of the caller's own event.
ERP stores no booking copy (one canonical store, no drift); the audit trail is Exchange's
(organiser, attendees, room response) + Error Log for failures.

GATED + FAIL-SAFE like the meeting overlay in pm.api.schedule: when ec_pm_calendar_sync is off
or Graph is not configured, reads return sync_on=False / room.error codes, never a 500.
Permissions: any PM user (PO 05/11: "ai cũng đặt, tự nhận"); writes only ever touch the
caller's own calendar. Needs Graph Application Calendars.ReadWrite (already used by RSVP)."""
import json

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, add_days, nowdate, now_datetime

from ecentric_workspace.pm import permissions as pmperm

DT = "EC Meeting Room"
TZ = "Asia/Ho_Chi_Minh"
GRAPH = "https://graph.microsoft.com/v1.0"
_PREFER = 'outlook.timezone="Asia/Ho_Chi_Minh"'
_CACHE_TTL = 60            # seconds: home card + room page are opened by everyone
_MAX_HOURS = 10
_PAST_GRACE_MIN = 5        # may book a slot that started a few minutes ago
_EV_FIELDS = "id,iCalUId,subject,start,end,organizer,showAs,isCancelled,isAllDay"


# ------------------------------------------------------------------ helpers
def _conf():
    return frappe.get_conf() if hasattr(frappe, "get_conf") else {}


def _graph_token(loud):
    """Token or None. loud=True (writes) -> friendly throw instead of None."""
    if not _conf().get("ec_pm_calendar_sync"):
        if loud:
            frappe.throw(_("Đồng bộ lịch Teams chưa được bật."))
        return None
    from ecentric_workspace.notification_center.providers import graph as msgraph
    if not msgraph.is_configured():
        if loud:
            frappe.throw(_("Chưa cấu hình kết nối Microsoft 365."))
        return None
    ok, token = msgraph.get_app_token()
    if not ok:
        if loud:
            frappe.throw(_("Không kết nối được Microsoft 365, thử lại sau."))
        return None
    return token


def _rooms(enabled_only=True):
    filters = {"enabled": 1} if enabled_only else {}
    rows = frappe.get_all(DT, filters=filters,
                          fields=["name", "room_code", "room_title", "email", "floor", "note",
                                  "capacity", "sort_order"],
                          order_by="sort_order asc, room_code asc", ignore_permissions=True) or []
    out = []
    for r in rows:
        code, title = r.get("room_code") or r["name"], r.get("room_title") or ""
        out.append({"name": r["name"], "code": code, "title": title,
                    "label": "{0} - {1}".format(code, title) if title else code,
                    "email": (r.get("email") or "").strip().lower(), "floor": r.get("floor") or "",
                    "note": r.get("note") or "", "capacity": r.get("capacity") or None})
    return out


def _room(name):
    for r in _rooms():
        if r["name"] == name or r["code"] == name:
            return r
    frappe.throw(_("Không tìm thấy phòng họp này."))


def _dt(v):
    """Graph dateTime ('2026-11-05T10:00:00.0000000') -> 'YYYY-MM-DD HH:MM:SS' (site local)."""
    return ((v or {}).get("dateTime") or "")[:19].replace("T", " ")


def _iso(local):
    return str(get_datetime(local)).replace(" ", "T")[:19]


def _view_url(email, start_local, end_local):
    from urllib.parse import quote
    return ("/users/" + quote(email) + "/calendarView?startDateTime=" + _iso(start_local) +
            "%2B07:00&endDateTime=" + _iso(end_local) + "%2B07:00&$select=" + _EV_FIELDS +
            "&$top=200&$orderby=start/dateTime")


def _busy_rows(events):
    out = []
    for ev in events or []:
        if ev.get("isCancelled") or (ev.get("showAs") or "busy") == "free":
            continue
        st, en = _dt(ev.get("start")), _dt(ev.get("end"))
        if not st or not en:
            continue
        org = ((ev.get("organizer") or {}).get("emailAddress") or {})
        out.append({"start": st, "end": en, "uid": ev.get("iCalUId") or ev.get("id") or "",
                    "who": org.get("name") or (ev.get("subject") or _("Đã có người đặt")),
                    "org": (org.get("address") or "").lower(), "all_day": bool(ev.get("isAllDay"))})
    return out


def _read_rooms(rooms, start_local, end_local, token):
    """{email: {"rows": [...]} | {"error": code}} - ONE Graph $batch for every room."""
    import requests
    reqs = [{"id": str(i), "method": "GET", "url": _view_url(r["email"], start_local, end_local),
             "headers": {"Prefer": _PREFER}} for i, r in enumerate(rooms)]
    out = {}
    try:
        res = requests.post(GRAPH + "/$batch", json={"requests": reqs}, timeout=15,
                            headers={"Authorization": "Bearer " + token,
                                     "Content-Type": "application/json"})
        if res.status_code != 200:
            return {r["email"]: {"error": "GRAPH_%s" % res.status_code} for r in rooms}
        by_id = {x.get("id"): x for x in (res.json().get("responses") or [])}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "rooms read")
        return {r["email"]: {"error": "GRAPH_EXC"} for r in rooms}
    for i, r in enumerate(rooms):
        x = by_id.get(str(i)) or {}
        st = x.get("status")
        if st == 200:
            out[r["email"]] = {"rows": _busy_rows((x.get("body") or {}).get("value"))}
        elif st == 404:
            out[r["email"]] = {"error": "ROOM_NOT_FOUND"}   # mailbox not created yet
        else:
            code = (((x.get("body") or {}).get("error") or {}).get("code")) or ""
            out[r["email"]] = {"error": "GRAPH_%s%s" % (st, (" " + code) if code else "")}
    return out


def _gen():
    try:
        return int(frappe.cache().get_value("ec_rooms_gen") or 0)
    except Exception:
        return 0


def clear_cache():
    """Called after a booking / cancel / room edit: next read goes to Graph."""
    try:
        frappe.cache().set_value("ec_rooms_gen", str(_gen() + 1))
    except Exception:
        pass


def _day_data(day, rooms, token, fresh=False):
    key = "ec_rooms_day:%s:%s" % (_gen(), day)
    if not fresh:
        try:
            raw = frappe.cache().get_value(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    data = _read_rooms(rooms, "%s 00:00:00" % day, "%s 00:00:00" % add_days(day, 1), token)
    try:
        frappe.cache().set_value(key, json.dumps(data), expires_in_sec=_CACHE_TTL)
    except Exception:
        pass
    return data


# ------------------------------------------------------------------ read
@frappe.whitelist()
def day(date=None):
    """All rooms for one day: {date, now, sync_on, rooms: [{name, code, title, label, floor,
    note, capacity, error?, bookings: [{start, end, who, mine, uid}]}]}.
    Shared by the room page, the schedule tab and the home card (60 s server cache)."""
    pmperm.require_pm_access()
    caller = (frappe.session.user or "").lower()
    d = str(getdate(date)) if date else nowdate()
    rooms = _rooms()
    token = _graph_token(False)
    data = _day_data(d, rooms, token) if (token and rooms) else {}
    out = []
    for r in rooms:
        x = data.get(r["email"]) or {}
        row = {k: r[k] for k in ("name", "code", "title", "label", "floor", "note", "capacity")}
        if not token:
            row["error"] = "SYNC_OFF"
        elif x.get("error"):
            row["error"] = x["error"]
        row["bookings"] = [{"start": b["start"], "end": b["end"], "who": b["who"],
                            "mine": b["org"] == caller, "uid": b["uid"], "all_day": b["all_day"]}
                           for b in (x.get("rows") or [])]
        out.append(row)
    return {"date": d, "now": str(now_datetime())[:19], "sync_on": bool(token), "rooms": out}


def _room_state(ev, room_emails):
    """accepted | declined | pending - the room's answer on one of the caller's events."""
    for a in ev.get("attendees") or []:
        addr = ((a.get("emailAddress") or {}).get("address") or "").lower()
        if addr in room_emails:
            resp = ((a.get("status") or {}).get("response") or "none")
            return {"accepted": "accepted", "declined": "declined"}.get(resp, "pending"), addr
    return None, None


@frappe.whitelist()
def mine(days=14):
    """The caller's upcoming room bookings (from their own calendar, so bookings made in Teams
    are listed too): {rows: [{event_id, uid, room, label, start, end, subject, state, join_url}]}."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    token = _graph_token(False)
    if not token:
        return {"rows": [], "sync_on": False}
    rooms = _rooms()
    by_email = {r["email"]: r for r in rooms}
    import requests
    from urllib.parse import quote
    start = str(now_datetime())[:19]
    end = "%s 00:00:00" % add_days(nowdate(), max(1, min(int(days or 14), 60)))
    url = (GRAPH + "/users/" + quote(caller) + "/calendarView?startDateTime=" + _iso(start) +
           "%2B07:00&endDateTime=" + _iso(end) + "%2B07:00&$select=id,iCalUId,subject,start,end,"
           "attendees,isOrganizer,isCancelled,onlineMeeting&$top=200&$orderby=start/dateTime")
    try:
        r = requests.get(url, timeout=12, headers={"Authorization": "Bearer " + token,
                                                   "Prefer": _PREFER})
        if r.status_code != 200:
            return {"rows": [], "error": "GRAPH_%s" % r.status_code}
        evs = r.json().get("value") or []
    except Exception:
        frappe.log_error(frappe.get_traceback(), "rooms mine")
        return {"rows": [], "error": "GRAPH_EXC"}
    rows = []
    for ev in evs:
        if ev.get("isCancelled") or not ev.get("isOrganizer"):
            continue
        state, addr = _room_state(ev, by_email)
        if not addr:
            continue
        rm = by_email[addr]
        rows.append({"event_id": ev.get("id"), "uid": ev.get("iCalUId") or "", "room": rm["name"],
                     "label": rm["label"], "start": _dt(ev.get("start")), "end": _dt(ev.get("end")),
                     "subject": ev.get("subject") or "", "state": state,
                     "join_url": ((ev.get("onlineMeeting") or {}) or {}).get("joinUrl") or ""})
    return {"rows": rows, "sync_on": True}


# ------------------------------------------------------------------ write
def _clean_window(start, end):
    try:
        s, e = get_datetime(start), get_datetime(end)
    except Exception:
        frappe.throw(_("Giờ họp không hợp lệ."))
    if not s or not e or e <= s:
        frappe.throw(_("Giờ kết thúc phải sau giờ bắt đầu."))
    if (e - s).total_seconds() > _MAX_HOURS * 3600:
        frappe.throw(_("Một lần đặt tối đa {0} giờ.").format(_MAX_HOURS))
    if (now_datetime() - s).total_seconds() > _PAST_GRACE_MIN * 60:
        frappe.throw(_("Không đặt được giờ đã qua."))
    return str(s)[:19], str(e)[:19]


def _clean_attendees(attendees, caller):
    if not attendees:
        return []
    try:
        lst = json.loads(attendees) if isinstance(attendees, str) else list(attendees)
    except Exception:
        frappe.throw(_("Danh sách người mời không hợp lệ."))
    out = []
    for em in lst:
        em = (em or "").strip().lower() if isinstance(em, str) else ""
        if not em or em == caller.lower() or em in out:
            continue
        u = frappe.db.get_value("User", em, ["enabled", "user_type"], as_dict=True)
        if not u or not u.get("enabled") or u.get("user_type") == "Website User":
            frappe.throw(_("Người được mời không hợp lệ: {0}").format(em))
        out.append(em)
    if len(out) > 50:
        frappe.throw(_("Mời tối đa 50 người."))
    return out


@frappe.whitelist(methods=["POST"])
def book(room, start, end, subject, attendees=None, teams=1):
    """Book a room = create a Teams/Outlook meeting on the CALLER'S calendar inviting the room.
    Re-checks the room calendar first (never trusts the page). The room then auto-accepts
    (state 'pending' until it does -> booking_state)."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    rm = _room(room)
    subject = (subject or "").strip()
    if not subject:
        frappe.throw(_("Ghi tên cuộc họp."))
    if len(subject) > 200:
        frappe.throw(_("Tên cuộc họp tối đa 200 ký tự."))
    s, e = _clean_window(start, end)
    people = _clean_attendees(attendees, caller)
    token = _graph_token(True)
    fresh = _read_rooms([rm], s, e, token).get(rm["email"]) or {}
    if fresh.get("error") == "ROOM_NOT_FOUND":
        frappe.throw(_("Phòng {0} chưa có trên Microsoft 365.").format(rm["label"]))
    if fresh.get("error"):
        frappe.throw(_("Chưa đọc được lịch phòng ({0}), thử lại sau.").format(fresh["error"]))
    clash = [b for b in fresh.get("rows") or [] if b["start"] < e and s < b["end"]]
    if clash:
        b = clash[0]
        frappe.throw(_("Phòng {0} đã có người đặt {1}–{2} ({3}).").format(
            rm["label"], b["start"][11:16], b["end"][11:16], b["who"]))
    body = {
        "subject": subject,
        "start": {"dateTime": _iso(s), "timeZone": TZ},
        "end": {"dateTime": _iso(e), "timeZone": TZ},
        "location": {"displayName": rm["label"], "locationEmailAddress": rm["email"],
                     "locationType": "conferenceRoom"},
        "attendees": [{"emailAddress": {"address": rm["email"], "name": rm["label"]},
                       "type": "resource"}] +
                     [{"emailAddress": {"address": p}, "type": "required"} for p in people],
        "allowNewTimeProposals": True,
    }
    if str(teams) not in ("0", "false", "False", ""):
        body.update({"isOnlineMeeting": True, "onlineMeetingProvider": "teamsForBusiness"})
    import requests
    from urllib.parse import quote
    try:
        r = requests.post(GRAPH + "/users/" + quote(caller) + "/events", json=body, timeout=15,
                          headers={"Authorization": "Bearer " + token,
                                   "Content-Type": "application/json", "Prefer": _PREFER})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "rooms book")
        frappe.throw(_("Không kết nối được Microsoft 365, thử lại sau."))
    if r.status_code not in (200, 201):
        code = ""
        try:
            code = ((r.json().get("error") or {}).get("code")) or ""
        except Exception:
            pass
        frappe.log_error("rooms.book %s -> HTTP %s %s" % (rm["code"], r.status_code, code),
                         "rooms book")
        frappe.throw(_("Chưa đặt được phòng (Microsoft 365 báo {0}).").format(r.status_code))
    ev = r.json() or {}
    clear_cache()
    return {"ok": True, "event_id": ev.get("id"), "uid": ev.get("iCalUId") or "",
            "room": rm["name"], "label": rm["label"], "start": s, "end": e, "subject": subject,
            "state": "pending",
            "join_url": ((ev.get("onlineMeeting") or {}) or {}).get("joinUrl") or ""}


def _own_event(event_id, token, select):
    import requests
    from urllib.parse import quote
    if not event_id:
        frappe.throw(_("Thiếu lịch họp."))
    url = (GRAPH + "/users/" + quote(frappe.session.user) + "/events/" +
           quote(event_id, safe="") + "?$select=" + select)
    r = requests.get(url, timeout=12, headers={"Authorization": "Bearer " + token,
                                               "Prefer": _PREFER})
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        frappe.throw(_("Chưa đọc được lịch họp (Microsoft 365 báo {0}).").format(r.status_code))
    return r.json() or {}


@frappe.whitelist()
def booking_state(event_id):
    """{state: accepted|declined|pending|cancelled} - the room's answer to one of MY bookings."""
    pmperm.require_pm_access()
    token = _graph_token(True)
    ev = _own_event(event_id, token, "attendees,isCancelled")
    if ev is None or ev.get("isCancelled"):
        return {"state": "cancelled"}
    state, _addr = _room_state(ev, {r["email"] for r in _rooms(enabled_only=False)})
    if state in ("accepted", "declined"):
        clear_cache()
    return {"state": state or "pending"}


@frappe.whitelist(methods=["POST"])
def cancel(event_id, comment=None):
    """Cancel MY booking (organiser only): Graph sends the cancellation to the room + guests."""
    pmperm.require_pm_access()
    token = _graph_token(True)
    ev = _own_event(event_id, token, "isOrganizer,isCancelled")
    if ev is None or ev.get("isCancelled"):
        clear_cache()
        return {"ok": True, "state": "cancelled"}
    if not ev.get("isOrganizer"):
        frappe.throw(_("Chỉ người đặt mới huỷ được phòng này."), frappe.PermissionError)
    import requests
    from urllib.parse import quote
    url = (GRAPH + "/users/" + quote(frappe.session.user) + "/events/" +
           quote(event_id, safe="") + "/cancel")
    r = requests.post(url, json={"comment": (comment or "")[:500]}, timeout=12,
                      headers={"Authorization": "Bearer " + token,
                               "Content-Type": "application/json"})
    if r.status_code not in (200, 202, 204):
        frappe.log_error("rooms.cancel -> HTTP %s" % r.status_code, "rooms cancel")
        frappe.throw(_("Chưa huỷ được (Microsoft 365 báo {0}).").format(r.status_code))
    clear_cache()
    return {"ok": True, "state": "cancelled"}

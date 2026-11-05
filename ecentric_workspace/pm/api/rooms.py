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
caller's own calendar. Needs Graph Application Calendars.ReadWrite (already used by RSVP).

v2 (06/11/2026, PO "đặt trên Teams hay ERP đơn giản y hệt nhau"): update() đổi giờ / đổi phòng /
tên / người mời (một buổi hoặc cả chuỗi), book(repeat=...) họp lặp lại (kiểm từng buổi), mời
khách ngoài công ty (email hợp lệ không phải user ERP), cancel(scope=series)."""
import json
import re

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
_BATCH_MAX = 20            # Graph JSON batching: at most 20 requests per $batch (else 400 for the whole batch)
_MAX_PAGES = 20            # @odata.nextLink pages followed per list ($top=200 -> 4000 events); more = error, never "free"


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


def _next_pages(body, token):
    """Events of a Graph list response + every @odata.nextLink page after it (capped).
    Returns (events, error_code_or_None)."""
    import requests
    evs = list((body or {}).get("value") or [])
    nxt, n = (body or {}).get("@odata.nextLink"), 0
    while nxt and n < _MAX_PAGES:
        n += 1
        try:
            r = requests.get(nxt, timeout=12, headers={"Authorization": "Bearer " + token, "Prefer": _PREFER})
        except Exception:
            frappe.log_error(frappe.get_traceback(), "rooms page")
            return evs, "GRAPH_EXC"
        if r.status_code != 200:
            return evs, "GRAPH_%s" % r.status_code
        j = r.json() or {}
        evs.extend(j.get("value") or [])
        nxt = j.get("@odata.nextLink")
    if nxt:
        frappe.log_error("rooms: more than %d pages, list cut" % _MAX_PAGES, "rooms page")
        return evs, "GRAPH_PAGES"
    return evs, None


def _get_list(url, token, timeout=12):
    """GET a Graph collection with paging. Returns (events, error_code_or_None)."""
    import requests
    try:
        r = requests.get(url, timeout=timeout, headers={"Authorization": "Bearer " + token, "Prefer": _PREFER})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "rooms list")
        return [], "GRAPH_EXC"
    if r.status_code != 200:
        return [], "GRAPH_%s" % r.status_code
    return _next_pages(r.json() or {}, token)


def _read_rooms(rooms, start_local, end_local, token):
    """{email: {"rows": [...]} | {"error": code}} - Graph $batch (<= 20 rooms per call) for every room;
    a room with more than one page of events follows @odata.nextLink."""
    out = {}
    for k in range(0, len(rooms), _BATCH_MAX):
        out.update(_read_batch(rooms[k:k + _BATCH_MAX], start_local, end_local, token))
    return out


def _read_batch(rooms, start_local, end_local, token):
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
            evs, err = _next_pages(x.get("body") or {}, token)
            # a half-read room must not look free: report the page error instead
            out[r["email"]] = {"error": err} if err else {"rows": _busy_rows(evs)}
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
    # the room list is part of the key: a room added / re-pointed without the DocType hook
    # (bulk edit, SQL) must not be served as "free" from a cache that never read it
    import hashlib
    sig = hashlib.md5(",".join(sorted(r["email"] for r in rooms)).encode()).hexdigest()[:10]
    key = "ec_rooms_day:%s:%s:%s" % (_gen(), day, sig)
    if not fresh:
        try:
            raw = frappe.cache().get_value(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    data = _read_rooms(rooms, "%s 00:00:00" % day, "%s 00:00:00" % add_days(day, 1), token)
    if any(v.get("error") and v["error"] != "ROOM_NOT_FOUND" for v in data.values()):
        return data   # transient Graph error (429 / 5xx / timeout): never cache it
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


def _guests(ev, room_emails):
    """Attendees except the room: [{email, name, external}] (external = no ERP user)."""
    out = []
    for a in ev.get("attendees") or []:
        em = ((a.get("emailAddress") or {}).get("address") or "").lower()
        if not em or em in room_emails or a.get("type") == "resource":
            continue
        out.append({"email": em, "name": (a.get("emailAddress") or {}).get("name") or em,
                    "external": _is_external(em)})
    return out


def _is_external(email):
    """Khách ngoài = no ERP user, or a Website User (same rule as _clean_attendees)."""
    t = frappe.db.get_value("User", email, "user_type")
    return not t or t == "Website User"


_MINE_FIELDS = ("id,iCalUId,subject,start,end,attendees,isOrganizer,isCancelled,onlineMeeting,"
                "type,seriesMasterId")


@frappe.whitelist()
def mine(days=14):
    """The caller's upcoming room bookings (from their own calendar, so bookings made in Teams
    are listed too): {rows: [{event_id, uid, room, label, start, end, subject, state, join_url,
    recurring, series_id, guests: [{email, name, external}]}]}."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    token = _graph_token(False)
    if not token:
        return {"rows": [], "sync_on": False}
    by_email = {r["email"]: r for r in _rooms()}
    from urllib.parse import quote
    start = str(now_datetime())[:19]
    try:
        days = int(days or 14)
    except (TypeError, ValueError):
        days = 14
    end = "%s 00:00:00" % add_days(nowdate(), max(1, min(days, 60)))
    url = (GRAPH + "/users/" + quote(caller) + "/calendarView?startDateTime=" + _iso(start) +
           "%2B07:00&endDateTime=" + _iso(end) + "%2B07:00&$select=" + _MINE_FIELDS +
           "&$top=200&$orderby=start/dateTime")
    evs, err = _get_list(url, token)
    if err and not evs:
        return {"rows": [], "error": err}
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
                     "join_url": ((ev.get("onlineMeeting") or {}) or {}).get("joinUrl") or "",
                     "recurring": ev.get("type") in ("occurrence", "exception", "seriesMaster"),
                     "series_id": ev.get("seriesMasterId") or (ev.get("id") if ev.get("type") == "seriesMaster" else ""),
                     "guests": _guests(ev, by_email)})
    return {"rows": rows, "sync_on": True}


# ------------------------------------------------------------------ write helpers
_EMAIL = re.compile(r"^[^@\s,;<>\"']+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_MAX_GUESTS = 50
_MAX_SERIES_DAYS = 180     # = room BookingWindowInDays (tao_phong_hop_exchange.ps1)
_MAX_OCCURRENCES = 200     # loop guard only: daily for 180 days = 181 buổi, every one is checked
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
REPEATS = ("none", "daily", "weekdays", "weekly", "biweekly", "monthly")


def _clean_window(start, end, allow_past=False):
    try:
        s, e = get_datetime(start), get_datetime(end)
    except Exception:
        frappe.throw(_("Giờ họp không hợp lệ."))
    if not s or not e or e <= s:
        frappe.throw(_("Giờ kết thúc phải sau giờ bắt đầu."))
    if (e - s).total_seconds() > _MAX_HOURS * 3600:
        frappe.throw(_("Một lần đặt tối đa {0} giờ.").format(_MAX_HOURS))
    if not allow_past and (now_datetime() - s).total_seconds() > _PAST_GRACE_MIN * 60:
        frappe.throw(_("Không đặt được giờ đã qua."))
    return str(s)[:19], str(e)[:19]


def _clean_attendees(attendees, caller, room_emails=()):
    """Emails to invite. ERP users must be active; anyone else = khách ngoài (valid email).
    A room mailbox is never a guest (it would book a 2nd room without the free check).
    Returns [{email, external}]."""
    if not attendees:
        return []
    try:
        lst = json.loads(attendees) if isinstance(attendees, str) else list(attendees)
    except Exception:
        frappe.throw(_("Danh sách người mời không hợp lệ."))
    if isinstance(lst, str):
        lst = [lst]
    if not isinstance(lst, list):
        frappe.throw(_("Danh sách người mời không hợp lệ."))
    room_emails = {(x or "").lower() for x in room_emails or ()}
    out, seen = [], set()
    for em in lst:
        em = (em or "").strip().lower() if isinstance(em, str) else ""
        if not em or em == (caller or "").lower() or em in seen:
            continue
        if len(out) >= _MAX_GUESTS:     # before any DB lookup: a huge list must not cost one query per email
            frappe.throw(_("Mời tối đa {0} người.").format(_MAX_GUESTS))
        if not _EMAIL.match(em):
            frappe.throw(_("Email không hợp lệ: {0}").format(em))
        if em in room_emails:
            frappe.throw(_("{0} là phòng họp: chọn phòng ở ô Phòng, không mời như khách.").format(em))
        u = frappe.db.get_value("User", em, ["enabled", "user_type"], as_dict=True)
        if u and not u.get("enabled"):
            frappe.throw(_("Tài khoản {0} đã khoá, không mời được.").format(em))
        seen.add(em)
        out.append({"email": em, "external": not u or u.get("user_type") == "Website User"})
    return out


def _attendee_rows(rm, people):
    return ([{"emailAddress": {"address": rm["email"], "name": rm["label"]}, "type": "resource"}] +
            [{"emailAddress": {"address": p["email"]}, "type": "required"} for p in people])


def _location(rm):
    return {"displayName": rm["label"], "locationEmailAddress": rm["email"],
            "locationType": "conferenceRoom"}


def _horizon():
    """Last day a room accepts (BookingWindowInDays counts from TODAY, not from the 1st meeting)."""
    return getdate(add_days(nowdate(), _MAX_SERIES_DAYS))


def _check_horizon(start_local):
    if getdate(str(start_local)[:10]) > _horizon():
        frappe.throw(_("Phòng chỉ nhận đặt trước tối đa {0} ngày (đến {1}).").format(
            _MAX_SERIES_DAYS, _horizon().strftime("%d/%m/%Y")))


def _recurrence(repeat, until, start):
    """Graph patternedRecurrence for the simple Teams choices, or None."""
    repeat = (repeat or "none").strip().lower()
    if repeat not in REPEATS:
        frappe.throw(_("Kiểu lặp lại không hợp lệ."))
    if repeat == "none":
        return None
    s = get_datetime(start)
    if not until:
        frappe.throw(_("Chọn ngày kết thúc lặp lại."))
    try:
        u = getdate(until)
    except Exception:
        frappe.throw(_("Ngày kết thúc lặp lại không hợp lệ."))
    if u < s.date():
        frappe.throw(_("Ngày kết thúc lặp lại phải sau ngày họp đầu tiên."))
    if u > _horizon():
        # Exchange (EnforceSchedulingHorizon) declines the WHOLE series if it ends past the window
        frappe.throw(_("Lặp lại tối đa đến {0}: phòng chỉ nhận đặt trước {1} ngày.").format(
            _horizon().strftime("%d/%m/%Y"), _MAX_SERIES_DAYS))
    if repeat == "weekdays" and s.weekday() >= 5:
        frappe.throw(_("Lặp các ngày trong tuần: ngày họp đầu phải từ thứ Hai đến thứ Sáu."))
    dow = _WEEKDAYS[s.weekday()]
    pattern = {
        "daily": {"type": "daily", "interval": 1},
        "weekdays": {"type": "weekly", "interval": 1, "daysOfWeek": _WEEKDAYS[:5], "firstDayOfWeek": "monday"},
        "weekly": {"type": "weekly", "interval": 1, "daysOfWeek": [dow], "firstDayOfWeek": "monday"},
        "biweekly": {"type": "weekly", "interval": 2, "daysOfWeek": [dow], "firstDayOfWeek": "monday"},
        "monthly": {"type": "absoluteMonthly", "interval": 1, "dayOfMonth": s.day},
    }[repeat]
    return {"pattern": pattern,
            "range": {"type": "endDate", "startDate": str(s.date()), "endDate": str(u)}}


def _occurrences(start, end, rec):
    """[(start, end)] local strings for a (simple) Graph recurrence; [(start, end)] if none."""
    s, e = get_datetime(start), get_datetime(end)
    if not rec:
        return [(str(s)[:19], str(e)[:19])]
    import datetime as _d
    p, rg = rec.get("pattern") or {}, rec.get("range") or {}
    first, last = getdate(rg.get("startDate") or s.date()), getdate(rg.get("endDate") or s.date())
    dur, tod = e - s, s.time()
    typ, step = p.get("type"), int(p.get("interval") or 1)
    days = [_WEEKDAYS.index(x) for x in (p.get("daysOfWeek") or []) if x in _WEEKDAYS]
    out, d = [], first
    week0 = first - _d.timedelta(days=first.weekday())
    while d <= last and len(out) < _MAX_OCCURRENCES:
        ok = False
        if typ == "daily":
            ok = (d - first).days % step == 0
        elif typ == "weekly":
            wk = ((d - _d.timedelta(days=d.weekday())) - week0).days // 7
            ok = d.weekday() in days and wk % step == 0
        elif typ == "absoluteMonthly":
            # Outlook/Exchange: day 29-31 in a shorter month falls on that month's last day
            months = (d.year - first.year) * 12 + d.month - first.month
            last_dom = (_d.date(d.year + d.month // 12, d.month % 12 + 1, 1) - _d.timedelta(days=1)).day
            ok = d.day == min(int(p.get("dayOfMonth") or first.day), last_dom) and months % step == 0
        if ok:
            st = _d.datetime.combine(d, tod)
            out.append((str(st)[:19], str(st + dur)[:19]))
        d += _d.timedelta(days=1)
    return out


def _fmt_day(local):
    return "{0}/{1}".format(local[8:10], local[5:7])


def _check_free(rm, slots, token, own_uids=(), own_slots=()):
    """Throw a friendly message when the room is busy in any slot (fresh Graph read, never the
    cache). Own meeting (uids / own current slots of the caller) is ignored when editing."""
    lo, hi = min(x[0] for x in slots), max(x[1] for x in slots)
    fresh = _read_rooms([rm], lo, hi, token).get(rm["email"]) or {}
    if fresh.get("error") == "ROOM_NOT_FOUND":
        frappe.throw(_("Phòng {0} chưa có trên Microsoft 365.").format(rm["label"]))
    if fresh.get("error"):
        frappe.throw(_("Chưa đọc được lịch phòng ({0}), thử lại sau.").format(fresh["error"]))
    caller = (frappe.session.user or "").lower()
    busy = [b for b in fresh.get("rows") or []
            if b["uid"] not in own_uids and not (b["org"] == caller and (b["start"], b["end"]) in own_slots)]
    hits = []
    for s, e in slots:
        for b in busy:
            if b["start"] < e and s < b["end"]:
                hits.append((s, b))
                break
    if not hits:
        return
    s0, b0 = hits[0]
    if len(slots) == 1:
        frappe.throw(_("Phòng {0} đã có người đặt {1}–{2} ({3}).").format(
            rm["label"], b0["start"][11:16], b0["end"][11:16], b0["who"]))
    days = ", ".join(_fmt_day(s) for s, _b in hits[:5]) + ("…" if len(hits) > 5 else "")
    frappe.throw(_("Phòng {0} đã có người đặt vào {1} buổi: {2}. Chọn giờ, phòng hoặc ngày kết thúc khác.")
                 .format(rm["label"], len(hits), days))


def _graph_write(method, url, token, body=None):
    import requests
    try:
        fn = getattr(requests, method)
        r = fn(url, json=body, timeout=15, headers={"Authorization": "Bearer " + token,
                                                    "Content-Type": "application/json",
                                                    "Prefer": _PREFER})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "rooms " + method)
        frappe.throw(_("Không kết nối được Microsoft 365, thử lại sau."))
    if r.status_code not in (200, 201, 202, 204):
        code = ""
        try:
            code = ((r.json().get("error") or {}).get("code")) or ""
        except Exception:
            pass
        frappe.log_error("rooms %s %s -> HTTP %s %s" % (method, url.split("/users/")[-1][:60],
                                                       r.status_code, code), "rooms write")
        frappe.throw(_("Microsoft 365 chưa nhận thay đổi (mã {0}).").format(r.status_code))
    try:
        return r.json() or {}
    except Exception:
        return {}


def _ev_url(event_id, suffix=""):
    from urllib.parse import quote
    return (GRAPH + "/users/" + quote(frappe.session.user) + "/events/" +
            quote(event_id, safe="") + suffix)


def _own_event(event_id, token, select):
    import requests
    if not event_id:
        frappe.throw(_("Thiếu lịch họp."))
    try:
        r = requests.get(_ev_url(event_id) + "?$select=" + select, timeout=12,
                         headers={"Authorization": "Bearer " + token, "Prefer": _PREFER})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "rooms event")
        frappe.throw(_("Không kết nối được Microsoft 365, thử lại sau."))
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        frappe.throw(_("Chưa đọc được lịch họp (Microsoft 365 báo {0}).").format(r.status_code))
    return r.json() or {}


def _series_instances(master_id, token, lo, hi):
    """The real occurrences of MY series in [lo, hi] from Graph: [(iCalUId, start, end)].
    Works for every pattern / range Teams can make (noEnd, numbered, relativeMonthly...)."""
    url = (_ev_url(master_id, "/instances") + "?startDateTime=" + _iso(lo) + "%2B07:00&endDateTime=" +
           _iso(hi) + "%2B07:00&$select=iCalUId,start,end,isCancelled&$top=200")
    vals, err = _get_list(url, token)
    if err:
        frappe.throw(_("Chưa đọc được các buổi của chuỗi họp ({0}), thử lại sau.").format(err))
    return [(v.get("iCalUId") or "", _dt(v.get("start")), _dt(v.get("end"))) for v in vals
            if not v.get("isCancelled") and _dt(v.get("start"))]


_DESC_MAX = 4000
_DESC_RX = re.compile(r'<div data-erp-desc="1">(.*?)</div><!--/erp-desc-->', re.S)
# Teams/Outlook append the join block after a long underscore rule ("____") in the body
_TEAMS_CUT = re.compile(r"_{20,}|Microsoft Teams (meeting|Need help)|Cuộc họp Microsoft Teams", re.I)


def _clean_desc(description):
    d = (description or "").replace("\r\n", "\n").strip()
    if len(d) > _DESC_MAX:
        frappe.throw(_("Mô tả tối đa {0} ký tự.").format(_DESC_MAX))
    return d


def _desc_html(text):
    """Plain text -> our own marked block (so a later edit replaces ONLY this part and keeps the
    Teams join block that Exchange appends to an online meeting's body)."""
    import html as _h
    inner = "<br>".join(_h.escape(line) for line in text.split("\n"))
    return '<div data-erp-desc="1">%s</div><!--/erp-desc-->' % inner


def _html_text(fragment):
    import html as _h
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", fragment or "")
    t = re.sub(r"<[^>]+>", "", t)
    t = _h.unescape(t).replace("\xa0", " ")
    return "\n".join(line.rstrip() for line in t.split("\n")).strip()


def _split_desc(body_html):
    """(description_text, editable, has_marker) from an event body."""
    content = body_html or ""
    m = _DESC_RX.search(content)
    if m:
        return _html_text(m.group(1)), True, True
    body = re.search(r"(?is)<body[^>]*>(.*)</body>", content)
    text = _html_text(body.group(1) if body else content)
    cut = _TEAMS_CUT.search(text)
    user = (text[:cut.start()] if cut else text).strip()
    # written in Teams/Outlook (no marker): show it, but edit it there (we cannot cut it out of
    # their HTML safely without risking the join block)
    return user, not user, False


def _with_desc(body_html, text):
    content = body_html or ""
    block = _desc_html(text) if text else ""
    if _DESC_RX.search(content):
        return _DESC_RX.sub(lambda _m: block, content, count=1)
    if not block:
        return content
    mb = re.search(r"(?i)<body[^>]*>", content)
    if mb:
        return content[:mb.end()] + block + content[mb.end():]
    return block + content


def _clean_subject(subject):
    subject = (subject or "").strip()
    if not subject:
        frappe.throw(_("Ghi tên cuộc họp."))
    if len(subject) > 200:
        frappe.throw(_("Tên cuộc họp tối đa 200 ký tự."))
    return subject


def _truthy(v):
    return str(v) not in ("0", "false", "False", "", "None")


# ------------------------------------------------------------------ write
@frappe.whitelist(methods=["POST"])
def book(room, start, end, subject, attendees=None, teams=1, repeat="none", repeat_until=None, txn=None,
         description=None):
    """Book a room = create a Teams/Outlook meeting on the CALLER'S calendar inviting the room
    (+ guests, internal or khách ngoài). repeat: none|daily|weekdays|weekly|biweekly|monthly
    until repeat_until (<= 180 days, the room's booking window). Re-checks EVERY occurrence
    against the room first (Exchange would decline the whole series on one clash). The room
    then auto-accepts (state 'pending' until it does -> booking_state)."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    rm = _room(room)
    subject = _clean_subject(subject)
    s, e = _clean_window(start, end)
    _check_horizon(s)
    people = _clean_attendees(attendees, caller, [r["email"] for r in _rooms(enabled_only=False)])
    rec = _recurrence(repeat, repeat_until, s)
    token = _graph_token(True)
    _check_free(rm, _occurrences(s, e, rec), token)
    body = {"subject": subject,
            "start": {"dateTime": _iso(s), "timeZone": TZ}, "end": {"dateTime": _iso(e), "timeZone": TZ},
            "location": _location(rm), "attendees": _attendee_rows(rm, people),
            "allowNewTimeProposals": True}
    desc = _clean_desc(description)
    if desc:
        body["body"] = {"contentType": "HTML", "content": _desc_html(desc)}
    if rec:
        body["recurrence"] = rec
    if txn and re.match(r"^[A-Za-z0-9-]{8,64}$", str(txn)):
        # Graph de-duplicates a POST /events retried with the same transactionId (timeout + click
        # again must not create two meetings). The dialog sends one id per opening.
        body["transactionId"] = str(txn)
    if _truthy(teams):
        body.update({"isOnlineMeeting": True, "onlineMeetingProvider": "teamsForBusiness"})
    from urllib.parse import quote
    ev = _graph_write("post", GRAPH + "/users/" + quote(caller) + "/events", token, body)
    clear_cache()
    return {"ok": True, "event_id": ev.get("id"), "uid": ev.get("iCalUId") or "",
            "room": rm["name"], "label": rm["label"], "start": s, "end": e, "subject": subject,
            "state": "pending", "recurring": bool(rec),
            "external": len([p for p in people if p["external"]]),
            "join_url": ((ev.get("onlineMeeting") or {}) or {}).get("joinUrl") or ""}


@frappe.whitelist(methods=["POST"])
def update(event_id, room=None, start=None, end=None, subject=None, attendees=None, scope="occurrence",
           description=None):
    """Change MY booking like in Teams: time, room, title, guests. Organiser only.
    scope=occurrence (this meeting / this one occurrence) | series (the whole recurring series:
    room, title, guests, time of day). The new room/time is re-checked against the room first;
    moving rooms swaps the resource attendee so the old room is freed and the new one answers."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    token = _graph_token(True)
    ev = _own_event(event_id, token, "id,iCalUId,subject,start,end,attendees,isOrganizer,isCancelled,"
                                     "type,seriesMasterId,recurrence")
    if ev is None or ev.get("isCancelled"):
        frappe.throw(_("Cuộc họp này đã bị huỷ hoặc không còn."))
    if not ev.get("isOrganizer"):
        frappe.throw(_("Chỉ người đặt mới sửa được cuộc họp này."), frappe.PermissionError)
    # the series master's id IS the series (e.g. the row of a series just booked): never patch the
    # master as if it were one meeting - that would move every occurrence after checking only one
    scope = "series" if (scope == "series" or ev.get("type") == "seriesMaster") else "occurrence"
    target = ev
    if scope == "series":
        master_id = ev.get("seriesMasterId") or (ev.get("id") if ev.get("type") == "seriesMaster" else None)
        if not master_id:
            frappe.throw(_("Cuộc họp này không lặp lại."))
        target = _own_event(master_id, token, "id,iCalUId,subject,start,end,attendees,isOrganizer,"
                                              "isCancelled,type,recurrence")
        if not target:
            frappe.throw(_("Không tìm thấy chuỗi họp."))
    all_rooms = _rooms(enabled_only=False)
    room_emails = {r["email"] for r in all_rooms}
    _st, cur_addr = _room_state(target, room_emails)
    cur_room = next((r for r in all_rooms if r["email"] == cur_addr), None)
    rm = _room(room) if room else cur_room
    if not rm:
        frappe.throw(_("Cuộc họp này chưa có phòng, chọn phòng."))
    old_s, old_e = _dt(target.get("start")), _dt(target.get("end"))
    if scope == "series" and (start or end):
        # series: keep the series' dates, change the time of day
        d0 = old_s[:10]
        ns = d0 + " " + str(get_datetime(start or old_s).time())[:8]
        ne_day = str(getdate(add_days(d0, (getdate((end or old_e)[:10]) - getdate((start or old_s)[:10])).days)))
        ne = ne_day + " " + str(get_datetime(end or old_e).time())[:8]
        s, e = _clean_window(ns, ne, allow_past=True)
    elif start or end:
        s, e = _clean_window(start or old_s, end or old_e)
        _check_horizon(s)
    else:
        s, e = old_s, old_e
    patch = {}
    if subject is not None:
        patch["subject"] = _clean_subject(subject)
    if description is not None:
        desc = _clean_desc(description)
        cur = _own_event(target["id"], token, "body") or {}
        cur_html = ((cur.get("body") or {}).get("content")) or ""
        old_text, editable, _mk = _split_desc(cur_html)
        if desc != old_text:
            if not editable:
                frappe.throw(_("Mô tả này được viết trên Teams/Outlook, hãy sửa ở đó."))
            patch["body"] = {"contentType": "HTML", "content": _with_desc(cur_html, desc)}
    if (s, e) != (old_s, old_e):
        patch["start"] = {"dateTime": _iso(s), "timeZone": TZ}
        patch["end"] = {"dateTime": _iso(e), "timeZone": TZ}
    room_changed = not cur_room or rm["email"] != cur_room["email"]
    if attendees is not None or room_changed:
        if attendees is not None:
            people = _clean_attendees(attendees, caller, room_emails)
        else:
            people = [{"email": g["email"], "external": g["external"]} for g in _guests(target, room_emails)]
        patch["attendees"] = _attendee_rows(rm, people)
    if room_changed:
        patch["location"] = _location(rm)
    if not patch:
        return {"ok": True, "unchanged": True, "event_id": target.get("id")}
    if room_changed or "start" in patch:
        if scope == "series":
            # the series' REAL future occurrences (Graph /instances, any Teams pattern or range) up to the
            # room's booking window, each moved to the new time of day when the time changes
            import datetime as _d
            now_s = str(now_datetime())[:19]
            inst = _series_instances(target["id"], token, now_s, "%s 23:59:59" % _horizon())
            dur, tod = get_datetime(e) - get_datetime(s), get_datetime(s).time()
            slots = []
            for _u, a, b in inst:
                if "start" in patch:
                    st = _d.datetime.combine(getdate(a[:10]), tod)
                    a, b = str(st)[:19], str(st + dur)[:19]
                if b > now_s:
                    slots.append((a, b))
            uids, own = {x[0] for x in inst if x[0]}, {(x[1], x[2]) for x in inst}
        else:
            slots = [(s, e)]
            uids, own = {ev.get("iCalUId")}, {(old_s, old_e)}
        if slots:
            _check_free(rm, slots, token, own_uids=uids if not room_changed else set(),
                        own_slots=own if not room_changed else set())
    _graph_write("patch", _ev_url(target["id"]), token, patch)
    clear_cache()
    return {"ok": True, "event_id": target.get("id"), "scope": scope, "room": rm["name"],
            "label": rm["label"], "start": s, "end": e, "state": "pending" if (room_changed or "start" in patch) else None}


@frappe.whitelist()
def detail(event_id):
    """Description of MY booking for the edit dialog: {description, editable}. Organiser only."""
    pmperm.require_pm_access()
    token = _graph_token(True)
    ev = _own_event(event_id, token, "body,isOrganizer,isCancelled")
    if ev is None or ev.get("isCancelled"):
        frappe.throw(_("Cuộc họp này đã bị huỷ hoặc không còn."))
    if not ev.get("isOrganizer"):
        frappe.throw(_("Chỉ người đặt mới xem được chi tiết này."), frappe.PermissionError)
    text, editable, _mk = _split_desc(((ev.get("body") or {}).get("content")) or "")
    return {"description": text, "editable": editable}


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
def cancel(event_id, comment=None, scope="occurrence"):
    """Cancel MY booking (organiser only): Graph sends the cancellation to the room + guests.
    scope=series cancels the whole recurring series."""
    pmperm.require_pm_access()
    token = _graph_token(True)
    ev = _own_event(event_id, token, "isOrganizer,isCancelled,type,seriesMasterId")
    if ev is None or ev.get("isCancelled"):
        clear_cache()
        return {"ok": True, "state": "cancelled"}
    if not ev.get("isOrganizer"):
        frappe.throw(_("Chỉ người đặt mới huỷ được phòng này."), frappe.PermissionError)
    if ev.get("type") == "seriesMaster":
        scope = "series"          # cancelling the master cancels the series: say so
    target = event_id
    if scope == "series":
        target = ev.get("seriesMasterId") or (event_id if ev.get("type") == "seriesMaster" else None)
        if not target:
            frappe.throw(_("Cuộc họp này không lặp lại."))
    _graph_write("post", _ev_url(target, "/cancel"), token, {"comment": (comment or "")[:500]})
    clear_cache()
    return {"ok": True, "state": "cancelled", "scope": "series" if scope == "series" else "occurrence"}

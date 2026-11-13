# Copyright (c) 2026, eCentric and contributors
"""Phòng họp - CHẾ ĐỘ ĐẶT TẠM khi Microsoft 365 lỗi (13/11/2026, sự cố Exchange/Graph toàn cầu).

Khi đọc lịch phòng từ Graph hỏng kiểu "tạm" (mất kết nối / timeout / 5xx) cho MỌI phòng, ERP bật cờ
"Microsoft đang lỗi" 120 giây (không chờ 15 s mỗi lần mở trang). Trong lúc đó:
  * day()  : phòng KHÔNG báo lỗi, khối bận = các lịch ĐẶT TẠM trên ERP; offline = True.
  * book() : lưu lịch ĐẶT TẠM (chặn trùng với lịch đặt tạm khác), state = "held".
  * mine() : các lịch đặt tạm của tôi (state "held"); huỷ được, sửa = huỷ rồi đặt lại.
Khi Graph chạy lại, sync_holds() (cron 5 phút) chuyển từng lịch đặt tạm thành lịch Teams thật
trên Outlook người đặt (mời phòng, link Teams, transactionId = mã đặt tạm -> Graph không tạo
trùng), kiểm trùng với lịch phòng trước; trùng -> báo người đặt. Lịch đã qua giờ -> bỏ.

Lưu ở __global defaults (JSON, không thêm DocType). Ép bật thủ công: Site Config
`ec_pm_rooms_offline = 1`.
"""
import json
import uuid

import frappe
from frappe import _
from frappe.utils import now_datetime

KEY = "ec_rooms_holds"
DOWN_KEY = "ec_rooms_graph_down"
DOWN_TTL = 120
PREFIX = "hold:"
HELD, SYNCED, DECLINED, FAILED, CANCELLED, EXPIRED = ("held", "synced", "declined", "failed",
                                                     "cancelled", "expired")
KEEP_DAYS = 14


# ------------------------------------------------------------------ Microsoft dang loi?
def transient(code):
    c = str(code or "")
    return c == "GRAPH_EXC" or c.startswith("GRAPH_5")     # 429 = bi han che tam: KHONG coi la Microsoft loi


def is_down():
    try:
        if (frappe.get_conf() or {}).get("ec_pm_rooms_offline"):
            return True
        return bool(frappe.cache().get_value(DOWN_KEY))
    except Exception:
        return False


def set_down(down=True):
    try:
        if down:
            frappe.cache().set_value(DOWN_KEY, "1", expires_in_sec=DOWN_TTL)
        else:
            frappe.cache().delete_value(DOWN_KEY)
    except Exception:
        pass


class GraphDown(Exception):
    pass


# ------------------------------------------------------------------ luu tru
def _load():
    try:
        v = json.loads(frappe.db.get_global(KEY) or "[]")
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _save(rows):
    import datetime as _d
    old = str((now_datetime() - _d.timedelta(days=KEEP_DAYS)))[:19]
    rows = [r for r in rows if r.get("status") == HELD or (r.get("end") or "") >= old]
    frappe.db.set_global(KEY, json.dumps(rows, ensure_ascii=False))


def all_holds(status=HELD):
    return [r for r in _load() if status is None or r.get("status") == status]


def overlaps(a_s, a_e, b_s, b_e):
    return a_s < b_e and b_s < a_e


def for_room_day(room_name, day):
    lo, hi = "%s 00:00:00" % day, "%s 23:59:59" % day
    return [r for r in all_holds() if r["room"] == room_name and overlaps(r["start"], r["end"], lo, hi)]


def as_booking(h, caller):
    return {"start": h["start"], "end": h["end"],
            "who": (h.get("org_name") or h["org"]) + " (đặt tạm)",
            "mine": h["org"] == caller, "uid": PREFIX + h["id"], "all_day": False}


def as_mine_row(h, rm_label):
    return {"event_id": PREFIX + h["id"], "uid": PREFIX + h["id"], "room": h["room"], "label": rm_label,
            "start": h["start"], "end": h["end"], "subject": h.get("subject") or "", "state": "held",
            "join_url": "", "recurring": False, "series_id": "",
            "guests": [{"email": e, "name": e, "external": False} for e in h.get("attendees") or []]}


def is_hold_id(event_id):
    return str(event_id or "").startswith(PREFIX)


def get(event_id):
    hid = str(event_id)[len(PREFIX):]
    return next((r for r in _load() if r["id"] == hid), None)


# ------------------------------------------------------------------ ghi
def create(rm, s, e, subject, people, description, teams, txn):
    """Luu lich dat tam (khoa phong de 2 nguoi bam cung luc khong cung lay)."""
    caller = frappe.session.user
    try:
        frappe.db.sql("select name from `tabEC Meeting Room` where name=%s for update", (rm["name"],))
    except Exception:
        pass
    rows = _load()
    for r in rows:
        if r.get("status") == HELD and r["room"] == rm["name"] and overlaps(s, e, r["start"], r["end"]):
            frappe.throw(_("Phòng {0} đã có người đặt tạm {1}–{2} ({3}).").format(
                rm["label"], r["start"][11:16], r["end"][11:16], r.get("org_name") or r["org"]))
    hid = uuid.uuid4().hex[:12]
    org_name = frappe.db.get_value("User", caller, "full_name") or caller
    rows.append({"id": hid, "room": rm["name"], "start": s, "end": e, "subject": subject,
                 "description": description or "", "attendees": [p["email"] for p in people],
                 "teams": 1 if teams else 0, "org": caller, "org_name": org_name,
                 "txn": str(txn) if txn else hid, "status": HELD, "event_id": "", "error": "",
                 "created": str(now_datetime())[:19]})
    _save(rows)
    return hid


def cancel(event_id):
    hid = str(event_id)[len(PREFIX):]
    rows = _load()
    for r in rows:
        if r["id"] == hid:
            if r["org"] != frappe.session.user:
                frappe.throw(_("Chỉ người đặt mới huỷ được phòng này."), frappe.PermissionError)
            if r["status"] == SYNCED and r.get("event_id"):
                return r["event_id"]      # da len Teams: huy that tren Graph
            r["status"] = CANCELLED
            _save(rows)
            return None
    return None


def _notify(user, title, msg):
    try:
        from ecentric_workspace.notification_center.events import publish_notification_event
        publish_notification_event("task_assigned", user, title, msg, action_url="/pm#rooms",
                                   dedupe_key="ec_rooms_hold:%s:%s" % (user, title[:60]))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "rooms hold notify")


def sync_holds():
    """cron */5: Microsoft chay lai -> dua lich dat tam len Teams/Outlook."""
    from ecentric_workspace.pm.api import rooms as R
    rows = _load()
    todo = [r for r in rows if r.get("status") == HELD]
    if not todo:
        return
    token = R._graph_token(False)
    if not token:
        return
    import requests
    from urllib.parse import quote
    now_s = str(now_datetime())[:19]
    rooms = {r["name"]: r for r in R._rooms(enabled_only=False)}
    changed = False
    for h in sorted(todo, key=lambda x: x.get("created") or ""):
        rm = rooms.get(h["room"])
        when = "%s %s–%s" % (h["start"][8:10] + "/" + h["start"][5:7], h["start"][11:16], h["end"][11:16])
        if h["end"] <= now_s:
            h["status"], changed = EXPIRED, True
            continue
        if not rm:
            h.update(status=FAILED, error="ROOM_NOT_FOUND")
            changed = True
            continue
        fresh = R._read_rooms([rm], h["start"], h["end"], token).get(rm["email"]) or {}
        if fresh.get("error"):
            if transient(fresh["error"]):
                set_down(True)
                break                   # van loi: lan sau thu lai
            h.update(status=FAILED, error=fresh["error"])
            changed = True
            continue
        clash = next((b for b in fresh.get("rows") or [] if overlaps(h["start"], h["end"], b["start"], b["end"])
                      and b["org"] != h["org"]), None)
        if clash:
            h.update(status=DECLINED, error="Trùng với %s %s–%s" % (clash["who"], clash["start"][11:16],
                                                                  clash["end"][11:16]))
            changed = True
            _notify(h["org"], "Lịch đặt tạm phòng %s bị trùng" % rm["label"],
                    "Lịch đặt tạm %s (%s) trùng với lịch có sẵn trên Teams (%s). Hãy chọn giờ hoặc phòng khác."
                    % (h.get("subject") or "", when, clash["who"]))
            continue
        body = {"subject": h.get("subject") or "Họp",
                "start": {"dateTime": R._iso(h["start"]), "timeZone": R.TZ},
                "end": {"dateTime": R._iso(h["end"]), "timeZone": R.TZ},
                "location": R._location(rm),
                "attendees": R._attendee_rows(rm, [{"email": x} for x in h.get("attendees") or []]),
                "allowNewTimeProposals": True, "transactionId": h.get("txn") or h["id"]}
        if h.get("description"):
            body["body"] = {"contentType": "HTML", "content": R._desc_html(h["description"])}
        if h.get("teams"):
            body.update({"isOnlineMeeting": True, "onlineMeetingProvider": "teamsForBusiness"})
        try:
            r = requests.post(R.GRAPH + "/users/" + quote(h["org"]) + "/events", json=body, timeout=20,
                              headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                                       "Prefer": R._PREFER})
        except Exception:
            set_down(True)
            break
        if r.status_code in (200, 201):
            ev = r.json() or {}
            h.update(status=SYNCED, event_id=ev.get("id") or "", error="")
            changed = True
            _notify(h["org"], "Lịch đặt tạm phòng %s đã lên Teams" % rm["label"],
                    "Microsoft đã chạy lại: lịch %s (%s) đã vào Outlook/Teams của bạn và người được mời."
                    % (h.get("subject") or "", when))
        elif r.status_code >= 500 or r.status_code == 429:   # thu lai lan sau
            set_down(True)
            break
        else:
            h.update(status=FAILED, error="HTTP %s" % r.status_code)
            changed = True
            frappe.log_error("rooms hold %s -> HTTP %s" % (h["id"], r.status_code), "rooms hold sync")
            _notify(h["org"], "Lịch đặt tạm phòng %s chưa lên Teams" % rm["label"],
                    "Lịch đặt tạm %s (%s) chưa chuyển được lên Teams (mã %s). Hãy đặt lại trên ERP hoặc Teams."
                    % (h.get("subject") or "", when, r.status_code))
    else:
        set_down(False)             # het vong khong gap loi tam: Microsoft da chay lai
    if changed:
        by = {r["id"]: r for r in todo}
        merged = _load()
        for r in merged:
            if r["id"] in by and r.get("status") == HELD:
                r.update(by[r["id"]])
        _save(merged)
        R.clear_cache()
        frappe.db.commit()

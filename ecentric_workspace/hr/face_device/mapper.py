# Copyright (c) 2026, eCentric and contributors
"""Doi payload cua may Hikvision -> su kien noi bo. KHONG import frappe.

Hai cua vao, cung mot dau ra `{"employee_no", "time", "major", "minor", "serial"}`:

- `from_push`: may tu day qua HTTP Listening. Tuy firmware, than request la
  multipart (phan `event_log` la JSON, kem anh), JSON tran, hoac XML
  `EventNotificationAlert`. Ten truong: `majorEventType` / `subEventType`.
- `from_sync`: nut dong bo doc `/ISAPI/AccessControl/AcsEvent` roi gui nguyen
  `InfoList`. Ten truong: `major` / `minor` / `time`.

Ten truong cua Hikvision dung lai o file nay - service khong biet toi chung.
"""
import datetime as dt
import json
import xml.etree.ElementTree as ET

from ecentric_workspace.hr.face_device.constants import MAJOR_EVENT

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


def _xml_to_dict(node):
    kids = list(node)
    if not kids:
        return (node.text or "").strip()
    out = {}
    for k in kids:
        out[_strip_ns(k.tag)] = _xml_to_dict(k)
    return out


def _load(text):
    text = (text or "").strip()
    if not text:
        return {}
    if text[0] in "{[":
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    if text[0] == "<":
        root = ET.fromstring(text)
        return {_strip_ns(root.tag): _xml_to_dict(root)}
    return {}


def _payload(form, raw):
    """Tim than su kien trong form (multipart / JSON da parse) hoac body tho."""
    form = form or {}
    for key in ("event_log", "AccessControllerEvent", "EventNotificationAlert"):
        val = form.get(key)
        if isinstance(val, (bytes, bytearray)):
            val = val.decode("utf-8", "replace")
        if isinstance(val, str) and val.strip()[:1] in ("{", "<"):
            return _load(val)
        if isinstance(val, dict):
            if key == "event_log":
                return val
            if key == "AccessControllerEvent":
                return dict(form)          # body JSON da duoc Frappe parse vao form_dict
            return {key: val}
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    return _load(raw)


def _event(ace, fallback_time=None):
    if not isinstance(ace, dict):
        return None
    emp = ace.get("employeeNoString") or ace.get("employeeNo")
    emp = str(emp).strip() if emp not in (None, "") else ""
    return {
        "employee_no": emp,
        "time": ace.get("time") or fallback_time or "",
        "major": _int(ace.get("major", ace.get("majorEventType"))),
        "minor": _int(ace.get("minor", ace.get("subEventType"))),
        "serial": _int(ace.get("serialNo")),
    }


def from_push(form, raw=None):
    """Mot request HTTP Listening -> 0 hoac 1 su kien. Heartbeat -> []."""
    data = _payload(form, raw)
    if "EventNotificationAlert" in data and isinstance(data["EventNotificationAlert"], dict):
        data = data["EventNotificationAlert"]
    ev = _event(data.get("AccessControllerEvent"), data.get("dateTime"))
    return [ev] if ev else []


def from_sync(items):
    """`InfoList` cua AcsEvent -> danh sach su kien."""
    out = []
    for it in items or []:
        ev = _event(it)
        if ev:
            out.append(ev)
    return out


def to_local(ts, tz_name):
    """'2026-10-12T08:45:12+07:00' -> datetime KHONG mui gio, theo gio he thong.

    May ghi kem mui gio: doi ve gio he thong de may cai sai mui gio van ra dung
    gio. Khong co mui gio thi coi la gio he thong. Sai dinh dang -> None.
    """
    s = str(ts or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        t = dt.datetime.fromisoformat(s.replace(" ", "T"))
    except ValueError:
        return None
    if t.tzinfo is not None:
        if ZoneInfo is None or not tz_name:
            return None
        t = t.astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)
    return t.replace(microsecond=0)


def is_pass(ev, minors):
    """Lan xac thuc THANH CONG co ma nhan vien = mot lan cham cong."""
    return (bool(ev.get("employee_no")) and ev.get("major") == MAJOR_EVENT
            and ev.get("minor") in minors)

# Copyright (c) 2026, eCentric and contributors
"""Khay tin nhan (C) + duong dan vao Raven (A): ham THUAN, khong import frappe.

Du lieu vao la dung nhung gi API cong khai cua Raven tra ve DUOI PHIEN nguoi dung
(gateway.py): Raven da loc kenh rieng / DM theo thanh vien, nen o day khong co
quyet dinh quyen nao - chi sap xep, cat gon, doi sang hinh dang trang can.
"""
import html
import json
import re
from urllib.parse import quote

from ecentric_workspace.chat import constants as C

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_MAX_ID = 140


def preview_text(details, limit=C.PREVIEW_LEN):
    """Doan xem truoc tu `last_message_details` cua Raven (JSON hoac dict). Rong khi khong co."""
    d = _details(details)
    if not d:
        return ""
    mtype = d.get("message_type") or "Text"
    if mtype != "Text":
        return C.MESSAGE_TYPE_LABELS.get(mtype, "[%s]" % mtype)
    text = _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", d.get("content") or ""))).strip()
    if len(text) > limit:
        text = text[:limit - 1].rstrip() + "…"
    return text


def _details(details):
    if isinstance(details, dict):
        return details
    if isinstance(details, str) and details.strip():
        try:
            v = json.loads(details)
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}
    return {}


def initials(name):
    words = [w for w in _WS_RE.split((name or "").strip()) if w and w[0].isalnum()]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[-1][0]).upper()


def _name_of(user_id, users):
    u = users.get(user_id) or {}
    return u.get("full_name") or user_id or ""


def _short_name(user_id, users):
    """Ten nguoi gui trong doan xem truoc cua kenh; cat bot khi qua dai."""
    n = _name_of(user_id, users)
    return n if len(n) <= 24 else n[:23] + "…"


def _sender_prefix(details, me, users, is_dm):
    d = _details(details)
    owner = d.get("owner")
    if not owner:
        return ""
    if owner == me:
        return "Bạn: "
    if is_dm:
        return ""
    if d.get("is_bot_message") and d.get("bot"):
        return "%s: " % d.get("bot")
    return "%s: " % _short_name(owner, users)


def _unread_map(unread_rows):
    out = {}
    for r in unread_rows or []:
        try:
            out[r.get("name")] = max(0, int(r.get("unread_count") or 0))
        except (TypeError, ValueError):
            continue
    return out


def _preview(details, me, users, is_dm):
    text = preview_text(details)
    return (_sender_prefix(details, me, users, is_dm) + text) if text else ""


def _item(ch, kind, me, users, unread):
    cid = ch.get("name")
    details = ch.get("last_message_details")
    if kind == "dm":
        peer = ch.get("peer_user_id") or me
        title = _name_of(peer, users)
        if ch.get("is_self_message") or peer == me:
            title = "%s (bạn)" % _name_of(me, users)
        avatar = (users.get(peer) or {}).get("user_image") or ""
        is_private = True
    else:
        title = ch.get("channel_name") or cid
        avatar = ""
        is_private = ch.get("type") == "Private"
    return {
        "id": cid,
        "kind": kind,
        "title": title,
        "is_private": bool(is_private),
        "unread": unread.get(cid, 0),
        "last_at": str(ch.get("last_message_timestamp") or ""),
        "preview": _preview(details, me, users, kind == "dm"),
        "avatar": avatar,
        "initials": initials(title),
        "href": "%s?c=%s" % (C.ROUTE, quote(cid or "", safe="")),
    }


def build_inbox(channels, dm_channels, unread_rows, users, me, limit=C.INBOX_LIMIT, unread_only=False):
    """{total_unread, items}: cuoc tro chuyen moi nhat truoc, bo kenh luu tru.

    total_unread dem tren MOI kenh co tin chua doc (khong chi `limit` dong dang hien), de so
    tren huy hieu khop voi Raven."""
    users = users or {}
    unread = _unread_map(unread_rows)
    items = []
    for ch in channels or []:
        if ch.get("is_archived"):
            continue
        items.append(_item(ch, "channel", me, users, unread))
    for ch in dm_channels or []:
        if ch.get("is_archived"):
            continue
        if not ch.get("last_message_timestamp"):
            continue                       # DM chua tung nhan tin: khong phai "gan day"
        items.append(_item(ch, "dm", me, users, unread))
    if unread_only:
        items = [i for i in items if i["unread"] > 0]
    # moi nhat truoc; chua co tin xuong cuoi; hoa thi chua doc truoc, roi theo ten (tat dinh)
    items.sort(key=lambda i: (i["last_at"] == "", _neg(i["last_at"]), -i["unread"], i["title"]))
    return {"total_unread": sum(unread.values()), "items": items[:max(0, int(limit or 0))]}


def _neg(ts):
    """Khoa sap xep giam dan cho chuoi thoi gian 'YYYY-MM-DD HH:MM:SS(.ffffff)'."""
    return tuple(-ord(c) for c in ts)


def safe_channel_id(value):
    """Ma kenh tu query string: chuoi, khong rong, khong qua dai, khong co '/'. Sai -> ''."""
    if not isinstance(value, str):
        return ""
    v = value.strip()
    if not v or len(v) > _MAX_ID or "/" in v or "\\" in v:
        return ""
    return v


def raven_path(channel_id, channels, dm_channels):
    """Duong dan nhung trong iframe cua trang /chat. Chi mo duoc kenh NAM TRONG danh sach Raven
    tra ve cho chinh nguoi nay - khong lo kenh rieng cua nguoi khac qua ma kenh. Khong thay ->
    trang dau cua Raven."""
    cid = safe_channel_id(channel_id)
    if cid:
        for ch in dm_channels or []:
            if ch.get("name") == cid:
                return "%s/dm-channel/%s" % (C.RAVEN_BASE, quote(cid, safe=""))
        for ch in channels or []:
            if ch.get("name") == cid and ch.get("workspace"):
                return "%s/%s/%s" % (C.RAVEN_BASE, quote(ch["workspace"], safe=""), quote(cid, safe=""))
    return C.RAVEN_BASE + "/"


#: Trang thai truy cap - quyet dinh THUAN tu 3 su that do gateway doc.
STATE_OK = "ok"
STATE_DISABLED = "disabled"
STATE_NOT_INSTALLED = "not_installed"
STATE_NO_ACCESS = "no_access"


def access_state(kill_switch_on, raven_installed, has_role):
    """Thu tu co chu dich: tat khan thang moi thu; chua cai Raven thi chua noi toi quyen."""
    if kill_switch_on:
        return STATE_DISABLED
    if not raven_installed:
        return STATE_NOT_INSTALLED
    if not has_role:
        return STATE_NO_ACCESS
    return STATE_OK


def state_message(state):
    return {
        STATE_DISABLED: C.MSG_DISABLED,
        STATE_NOT_INSTALLED: C.MSG_NOT_INSTALLED,
        STATE_NO_ACCESS: C.MSG_NO_ACCESS,
    }.get(state, "")

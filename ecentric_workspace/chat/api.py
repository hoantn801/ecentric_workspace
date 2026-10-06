# Copyright (c) 2026, eCentric and contributors
"""HTTP cua Chat noi bo. Hai ham DOC (GET), lay nguoi dung tu PHIEN, tra {success, message, data}.

    get_unread_total  -> {state, total}           huy hieu tren thanh tren + muc menu
    get_inbox         -> {state, total_unread, items}   khay tha xuong (C)

`state` != "ok" KHONG phai loi: trang hien thong diep tuong ung (tam tat / chua cai /
chua co quyen). Loi khi goi Raven -> success False + thong diep doc duoc; Error Log ghi
toi da 1 lan / 10 phut (hai ham nay chay o MOI lan tai trang, khong de ngap log).
"""
import frappe

from ecentric_workspace.chat import constants as C
from ecentric_workspace.chat import gateway as G
from ecentric_workspace.chat import inbox as I

_LOG_KEY = "ec_chat_api_logged"
_LOG_TTL = 600


def _ok(data):
    return {"success": True, "message": "", "data": data}


def _fail(message, status=None):
    if status:
        frappe.local.response["http_status_code"] = status
    return {"success": False, "message": message, "data": None}


def _log_once():
    try:
        cache = frappe.cache()
        if cache.get_value(_LOG_KEY):
            return
        cache.set_value(_LOG_KEY, 1, expires_in_sec=_LOG_TTL)
        frappe.log_error(title="ec_chat")
    except Exception:
        pass


def _guard():
    """None khi duoc goi tiep; nguoc lai la phan hoi tra ngay."""
    if frappe.session.user == "Guest":
        return _fail("Cần đăng nhập.", 403)
    st = G.state()
    if st != I.STATE_OK:
        return _ok({"state": st, "message": I.state_message(st), "total": 0, "total_unread": 0, "items": []})
    return None


@frappe.whitelist(methods=["GET"])
def get_unread_total():
    early = _guard()
    if early:
        return early
    try:
        total = sum(max(0, int(r.get("unread_count") or 0)) for r in G.unread_rows())
    except Exception:
        _log_once()
        return _fail(C.MSG_LOAD_FAILED)
    return _ok({"state": I.STATE_OK, "total": total})


@frappe.whitelist(methods=["GET"])
def get_inbox(unread_only=0):
    early = _guard()
    if early:
        return early
    try:
        channels, dms = G.list_channels()
        box = I.build_inbox(channels, dms, G.unread_rows(), G.user_cards(), frappe.session.user,
                            limit=C.INBOX_LIMIT, unread_only=str(unread_only) in ("1", "true", "True"))
    except Exception:
        _log_once()
        return _fail(C.MSG_LOAD_FAILED)
    box["state"] = I.STATE_OK
    return _ok(box)

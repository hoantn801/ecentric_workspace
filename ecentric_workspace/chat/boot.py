# Copyright (c) 2026, eCentric and contributors
"""Hai hook cua lop "ruot" Raven (xem raven_skin.py). Loi bat ky -> bo qua: boot / response cua
Frappe KHONG BAO GIO duoc vo vi lop nay; chi trang /raven bi dung toi.

extend_bootinfo  frappe.sessions.get() goi MOI lan (ca khi boot lay tu cache), SAU khi da ghi
                 cache -> thay doi chi song trong request nay. Phu ban dich tieng Viet.
after_request    chen <link> CSS mau ERP + <script src> noi ban dich vao HTML trang /raven.
"""
import frappe

from ecentric_workspace.chat import constants as C
from ecentric_workspace.chat import raven_skin as S


def _request_path():
    req = getattr(frappe.local, "request", None)
    return getattr(req, "path", "") or ""


def _skin_off():
    return bool(frappe.conf.get(C.SKIN_KILL_SWITCH))


def _warn(msg):
    try:
        frappe.logger("ec_chat").warning(msg, exc_info=True)
    except Exception:
        pass


def extend_bootinfo(bootinfo):
    try:
        if not S.is_raven_path(_request_path()) or _skin_off():
            return
        vi = S.load_vi(C.RAVEN_VI_FILE)
        if vi:
            bootinfo["__messages"] = S.overlay(bootinfo.get("__messages"), vi)
    except Exception:
        _warn("extend_bootinfo raven vi skipped")


def after_request(response=None, request=None):
    try:
        if response is None or request is None:
            return
        if not S.is_raven_path(getattr(request, "path", "")):
            return
        if getattr(response, "status_code", 0) != 200 or getattr(response, "is_streamed", False):
            return
        if getattr(response, "direct_passthrough", False):
            return
        if (getattr(response, "mimetype", "") or "") != "text/html" or _skin_off():
            return
        html = S.inject_page(response.get_data(as_text=True),
                             S.asset_url(C.RAVEN_BOOT_JS), S.asset_url(C.SKIN_CSS))
        if html is not None:
            response.set_data(html)
    except Exception:
        _warn("after_request raven skin skipped")

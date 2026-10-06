# Copyright (c) 2026, eCentric and contributors
"""Trang A - /chat: Raven nhung trong vo shell ERP (PO chot 05/10/2026).

NGUON TRANG NAM TRONG REPO (A65): template Jinja cua app (www/chat), server ve san trang thai
dau (khung nhung Raven, hoac thong diep tam tat / chua co quyen). Khong co Web Page tren site,
khong co patch sync. JS duy nhat cua trang la ec_chat.js dung chung (o thanh tren).

Raven chay trong <iframe> cung ten mien (X-Frame-Options SAMEORIGIN da cho phep - do
04/10/2026). Quyen kenh rieng / DM do chinh Raven kiem trong iframe.

no_cache BAT BUOC: HTML khac nhau theo nguoi (trang thai quyen, kenh mo san).
"""
import hashlib
import io
import os

import frappe

from ecentric_workspace.chat import constants as C
from ecentric_workspace.chat import gateway as G
from ecentric_workspace.chat import inbox as I

_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CSS = "public/css/ec_chat_page.css"
_VERSION = {}
MOUNT = '<aside class="ec-shell-mount" data-ec-shell="1" aria-label="Điều hướng eCentric"></aside>'


def _css_url():
    if "v" not in _VERSION:
        try:
            with io.open(os.path.join(_APP, _CSS), "rb") as fh:
                _VERSION["v"] = hashlib.md5(fh.read()).hexdigest()[:10]
        except Exception:
            _VERSION["v"] = "0"
    return "/assets/ecentric_workspace/%s?v=%s" % (_CSS.replace("public/", "", 1), _VERSION["v"])


def _require_login():
    if frappe.session.user == "Guest":
        from urllib.parse import quote
        frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(C.ROUTE, safe="/")
        raise frappe.Redirect


def _shell(context):
    from ecentric_workspace.shell import fallback as fb
    from ecentric_workspace.shell import server_nav
    mount = MOUNT
    try:
        mount = server_nav.rebuild_mount(MOUNT, C.ROUTE) or MOUNT
    except Exception:
        pass
    try:
        topbar = fb.render_topbar_inner(C.ROUTE, None, chat=G.chat_enabled())
    except Exception:
        topbar = ""
    context.ecc_shell_mount = mount
    context.ecc_topbar = topbar
    context.ecc_css = _css_url()
    context.no_cache = 1
    context.show_sidebar = 0


def _frame_src(state, channel_arg):
    """Duong dan iframe. Chi tra cuu danh sach kenh khi co ?c= (mo thang mot kenh tu khay C)."""
    if state != I.STATE_OK:
        return ""
    if not I.safe_channel_id(channel_arg):
        return C.RAVEN_BASE + "/"
    try:
        channels, dms = G.list_channels()
    except Exception:
        return C.RAVEN_BASE + "/"          # Raven tu mo trang dau; khong vo trang ERP
    return I.raven_path(channel_arg, channels, dms)


def get_context(context):
    _require_login()
    state = G.state()
    src = _frame_src(state, frappe.form_dict.get("c"))
    context.title = "Chat nội bộ"
    context.chat_state = state
    context.chat_message = I.state_message(state)
    context.chat_src = src
    _shell(context)
    return context

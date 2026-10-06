# Copyright (c) 2026, eCentric and contributors
"""Ho tro chung cho 4 trang www/tin_noi_bo/*: vo shell, ma phien ban asset, chan Guest.

NGUON TRANG NAM TRONG REPO (A65): trang la template Jinja cua app (www/), server ve san moi
trang thai dau (danh sach, so luot xem, cam xuc, nhan "Chua xem") - JS chi gui POST va cap
nhat con so, khong dung lai bo cuc. Khong co Web Page tren site, khong co patch sync.

no_cache BAT BUOC tren moi trang: @cache_html cua Frappe luu HTML theo DUONG DAN, dung chung
cho moi nguoi - thieu no thi nguoi thu hai thay danh sach / ten / luot xem cua nguoi thu nhat.
"""
import hashlib
import io
import os

import frappe

from ecentric_workspace.chat.gateway import chat_enabled  # o Tin nhan (05/10/2026)

from ecentric_workspace.internal_posts import constants as C

_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = {"css": "public/css/ec_internal_posts.css", "js": "public/js/ec_internal_posts.js",
          "editor": "public/js/ec_internal_posts_editor.js", "aiw": "public/js/ec_internal_posts_aiw.js"}
_VERSIONS = {}
MOUNT = '<aside class="ec-shell-mount" data-ec-shell="1" aria-label="Điều hướng eCentric"></aside>'


def asset_version(key):
    """md5 ngan cua tep - doi noi dung la doi ?v=, trinh duyet khong giu ban cu."""
    if key not in _VERSIONS:
        try:
            with io.open(os.path.join(_APP, ASSETS[key]), "rb") as fh:
                _VERSIONS[key] = hashlib.md5(fh.read()).hexdigest()[:10]
        except Exception:
            _VERSIONS[key] = "0"
    return _VERSIONS[key]


def asset_url(key):
    return "/assets/ecentric_workspace/%s?v=%s" % (ASSETS[key].replace("public/", "", 1), asset_version(key))


def require_login(route):
    """Guest -> trang dang nhap, quay lai dung trang nay sau khi dang nhap."""
    if frappe.session.user == "Guest":
        from urllib.parse import quote
        frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(route, safe="/")
        raise frappe.Redirect


def shell(context, route, detail=""):
    """Menu trai + thanh tren tu registry HIEN HANH (cung ham voi update_website_context)."""
    from ecentric_workspace.shell import fallback as fb
    from ecentric_workspace.shell import server_nav
    mount = MOUNT
    try:
        mount = server_nav.rebuild_mount(MOUNT, C.ROUTE) or MOUNT
    except Exception:
        pass
    detail_html = fb.make_detail(fb._esc(detail)) if detail else None
    try:
        topbar = fb.render_topbar_inner(C.ROUTE, detail_html, chat=chat_enabled())
    except Exception:
        topbar = ""
    context.ip_shell_mount = mount
    context.ip_topbar = topbar
    context.ip_css = asset_url("css")
    context.ip_js = asset_url("js")
    context.no_cache = 1
    context.show_sidebar = 0
    return context


def arg(name, default=""):
    v = frappe.form_dict.get(name)
    return default if v is None else str(v)

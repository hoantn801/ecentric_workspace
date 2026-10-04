# Copyright (c) 2026, eCentric and contributors
"""Ho tro chung cho cac trang www/bang_tin/*: vo shell, ma phien ban asset, chan Guest.

NGUON TRANG NAM TRONG REPO (A65): template Jinja cua app, server ve san moi trang thai dau. JS chi
goi POST va thay khoi HTML server ve lai. Khong co Web Page tren site, khong co patch sync.

no_cache BAT BUOC tren moi trang (bang tin khac nhau theo nguoi xem)."""
import hashlib
import io
import os

import frappe

from ecentric_workspace.social import constants as C

_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = {"css": "public/css/ec_social.css", "js": "public/js/ec_social.js"}
_VERSIONS = {}
MOUNT = '<aside class="ec-shell-mount" data-ec-shell="1" aria-label="Điều hướng eCentric"></aside>'


def asset_version(key):
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
    if frappe.session.user == "Guest":
        from urllib.parse import quote
        frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(route, safe="/")
        raise frappe.Redirect


def shell(context, detail=""):
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
        topbar = fb.render_topbar_inner(C.ROUTE, detail_html)
    except Exception:
        topbar = ""
    context.soc_shell_mount = mount
    context.soc_topbar = topbar
    context.soc_css = asset_url("css")
    context.soc_js = asset_url("js")
    context.no_cache = 1
    context.show_sidebar = 0
    return context


def arg(name, default=""):
    v = frappe.form_dict.get(name)
    return default if v is None else str(v)


def guard(fn, *args, **kwargs):
    """Goi service cho trang: Forbidden -> 403 doc duoc, NotFound -> 404."""
    from ecentric_workspace.social.domain import Forbidden, NotFound
    try:
        return fn(*args, **kwargs)
    except Forbidden as e:
        raise frappe.PermissionError(str(e))
    except NotFound as e:
        raise frappe.PageDoesNotExistError(str(e))

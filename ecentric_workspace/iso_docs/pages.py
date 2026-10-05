# Copyright (c) 2026, eCentric and contributors
"""Ho tro chung cho 3 trang www/tai_lieu/*: vo shell, ma phien ban asset, chan Guest.

Trang la template Jinja cua app (server ve san moi trang thai). JS chi ve so do mermaid, to sang
theo vai tro, bam buoc duyet va nhap goi. no_cache BAT BUOC: @cache_html luu theo duong dan,
dung chung cho moi nguoi.
"""
import hashlib
import io
import os

import frappe

ROUTE = "/tai-lieu"
_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = {"css": "public/css/ec_iso_docs.css", "js": "public/js/ec_iso_docs.js"}
_VERSIONS = {}
MOUNT = '<aside class="ec-shell-mount" data-ec-shell="1" aria-label="Điều hướng eCentric"></aside>'
#: thu vien ve so do (cdnjs, ban co dinh). securityLevel strict o JS.
MERMAID_JS = "https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js"


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


def shell(context, route=ROUTE, detail=""):
    from ecentric_workspace.shell import fallback as fb
    from ecentric_workspace.shell import server_nav
    mount = MOUNT
    try:
        mount = server_nav.rebuild_mount(MOUNT, route) or MOUNT
    except Exception:
        pass
    detail_html = fb.make_detail(fb._esc(detail)) if detail else None
    try:
        topbar = fb.render_topbar_inner(route, detail_html)
    except Exception:
        topbar = ""
    context.iso_shell_mount = mount
    context.iso_topbar = topbar
    context.iso_css = asset_url("css")
    context.iso_js = asset_url("js")
    context.no_cache = 1
    context.show_sidebar = 0
    return context


def arg(name, default=""):
    v = frappe.form_dict.get(name)
    return default if v is None else str(v)

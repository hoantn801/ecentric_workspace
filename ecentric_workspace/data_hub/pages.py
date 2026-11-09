# Copyright (c) 2026, eCentric and contributors
"""Ho tro chung cho 4 trang www/du_lieu/*: vo shell ERP, asset, chan Guest.

NGUON TRANG NAM TRONG REPO (A65): trang la template Jinja cua app (www/ + templates/includes/data_hub/),
server ve san trang thai dau (KPI, bang, kanban, quy tac). JS (ec_data_hub.bundle.js) chi loc / mo
popup / gui POST. Khong co Web Page tren site, khong co patch sync.

ASSET: ec_data_hub.bundle.js / .css CHI nap tren 4 trang nay (khong vao web_include cua moi trang).
`bench build` bam ten (dist/.../ec_data_hub.bundle.<hash>.js, assets.json) -> asset_url() lay ban bam;
chua build (may dev) thi ve tep goc kem ?v=md5.

no_cache BAT BUOC: @cache_html cua Frappe luu HTML theo DUONG DAN, dung chung cho moi nguoi.
"""
import hashlib
import io
import os

import frappe

from ecentric_workspace.data_hub import constants as C

_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = {"css": ("ec_data_hub.bundle.css", "public/css/ec_data_hub.bundle.css"),
          "js": ("ec_data_hub.bundle.js", "public/js/ec_data_hub.bundle.js")}
_VERSIONS = {}
MOUNT = '<aside class="ec-shell-mount" data-ec-shell="1" aria-label="Điều hướng eCentric"></aside>'


def _md5(rel):
    if rel not in _VERSIONS:
        try:
            with io.open(os.path.join(_APP, rel), "rb") as fh:
                _VERSIONS[rel] = hashlib.md5(fh.read()).hexdigest()[:10]
        except Exception:
            _VERSIONS[rel] = "0"
    return _VERSIONS[rel]


def asset_url(key):
    bundle, rel = ASSETS[key]
    try:
        from frappe.utils import get_assets_json
        hashed = (get_assets_json() or {}).get(bundle)
        if hashed:
            return hashed
    except Exception:
        pass
    return "/assets/ecentric_workspace/%s?v=%s" % (rel.replace("public/", "", 1), _md5(rel))


def require_login(route):
    if frappe.session.user == "Guest":
        from urllib.parse import quote
        frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(route, safe="/")
        raise frappe.Redirect


def shell(context, route, detail=""):
    """Menu trai + thanh tren tu registry hien hanh (giong feedback/pages.py)."""
    from ecentric_workspace.shell import fallback as fb
    from ecentric_workspace.shell import server_nav
    mount = MOUNT
    try:
        mount = server_nav.rebuild_mount(MOUNT, route) or MOUNT
    except Exception:
        pass
    try:
        from ecentric_workspace.chat.gateway import chat_enabled
        chat = chat_enabled()
    except Exception:
        chat = False
    detail_html = fb.make_detail(fb._esc(detail)) if detail else None
    try:
        topbar = fb.render_topbar_inner(route, detail_html, chat=chat)
    except Exception:
        topbar = ""
    context.edh_shell_mount = mount
    context.edh_topbar = topbar
    context.edh_css = asset_url("css")
    context.edh_js = asset_url("js")
    context.no_cache = 1
    context.show_sidebar = 0
    return context


def arg(name, default=""):
    v = frappe.form_dict.get(name)
    return default if v is None else str(v)


def render(context, route, build, title, detail=""):
    """Khung chung cua get_context: dang nhap, goi service, loi quyen -> trang than thien."""
    from ecentric_workspace.data_hub import service as S
    require_login(route)
    try:
        ctx = build()
    except S.Forbidden as e:
        raise frappe.PermissionError(str(e))
    context.update(ctx)
    context.title = title
    shell(context, route, detail=detail)
    return context

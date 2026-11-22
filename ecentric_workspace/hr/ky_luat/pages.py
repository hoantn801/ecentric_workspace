# Copyright (c) 2026, eCentric and contributors
"""Ho tro chung cho 2 trang www/ky_luat/*: vo shell ERP, ma phien ban asset, chan Guest.

NGUON TRANG NAM TRONG REPO (A65): template Jinja cua app (www/ky_luat + templates/includes/
ky_luat), server ve san trang thai dau (danh sach the vang / ho so, quyen, ghi chu phap ly).
JS (public/js/ec_ky_luat.js) chi mo popup chi tiet, gui POST, tai lai. Khong co Web Page tren
site, khong patch sync, khong khoi <script>/<style> inline.

no_cache BAT BUOC: @cache_html cua Frappe luu HTML theo duong dan, dung chung cho moi nguoi."""
import hashlib
import io
import json
import os

import frappe

from ecentric_workspace.hr.ky_luat import constants as C

_APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = {"css": "public/css/ec_ky_luat.css", "js": "public/js/ec_ky_luat.js"}
_VERSIONS = {}
MOUNT = '<aside class="ec-shell-mount" data-ec-shell="1" aria-label="Điều hướng eCentric"></aside>'


def asset_url(key):
    rel = ASSETS[key]
    if rel not in _VERSIONS:
        try:
            with io.open(os.path.join(_APP, rel), "rb") as fh:
                _VERSIONS[rel] = hashlib.md5(fh.read()).hexdigest()[:10]
        except Exception:
            _VERSIONS[rel] = "0"
    return "/assets/ecentric_workspace/%s?v=%s" % (rel.replace("public/", "", 1), _VERSIONS[rel])


def require_login(route):
    if frappe.session.user == "Guest":
        from urllib.parse import quote
        frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(route, safe="/")
        raise frappe.Redirect


def arg(name, default=""):
    v = frappe.form_dict.get(name)
    return default if v is None else str(v)


def shell(context, route, detail=""):
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
    context.ekl_shell_mount = mount
    context.ekl_topbar = topbar
    context.ekl_css = asset_url("css")
    context.ekl_js = asset_url("js")
    context.no_cache = 1
    context.show_sidebar = 0
    return context


def boot_json(data):
    """JSON cho <script type="application/json"> - chan dong the </script> trong du lieu."""
    return json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/")


def render_index(context):
    from ecentric_workspace.hr.ky_luat.application import views
    from ecentric_workspace.hr.ky_luat.infrastructure.repository import Repository
    require_login(C.ROUTE)
    repo = Repository()
    ctx = views.make_ctx(repo, frappe.session.user)
    data = views.index_page(repo, ctx, tab=arg("tab"), code=arg("ma"))
    context.update(data)
    context.boot_json = boot_json(data["boot"])
    context.title = "Kỷ luật lao động"
    shell(context, C.ROUTE)
    return context


def render_decision(context):
    """Trang quyet dinh (route cua EC Approval Type DISCIPLINE_DECISION): chi tiet phieu engine
    qua facade dung chung (kiem quyen xem cua engine) + nut CEO."""
    from ecentric_workspace.approval_center.shared.facade import APPROVAL_FACADE
    from ecentric_workspace.approval_center.shared.registry import get_definition
    require_login(C.ROUTE_DECISION)
    name = arg("id")
    context.title = "Quyết định kỷ luật"
    context.legal_note = C.LEGAL_NOTE
    if not name:
        raise frappe.DoesNotExistError("Thiếu mã phiếu (?id=).")
    detail = APPROVAL_FACADE.detail(get_definition("DISCIPLINE_DECISION"), name)
    biz = detail.get("business") or {}
    caps = detail.get("capabilities") or {}
    context.d = biz
    context.approval = detail.get("approval") or {}
    context.timeline = detail.get("timeline") or []
    context.attachments = detail.get("attachments") or []
    context.caps = caps
    context.case_route = (detail.get("extra") or {}).get("case_route") or C.ROUTE
    context.boot_json = boot_json({"name": name, "case": biz.get("discipline_case"),
                                   "doctype": detail.get("business_doctype"),
                                   "can_decide": bool(caps.get("can_approve"))})
    shell(context, C.ROUTE_DECISION, detail=name)
    return context

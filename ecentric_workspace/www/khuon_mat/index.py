# Copyright (c) 2026, eCentric and contributors
"""/khuon-mat - gui anh khuon mat cho may cham cong (ec-face-photo-v1, 05/11/2026).

Route: hooks.website_route_rules /khuon-mat -> khuon_mat. Nhan vien: chup / chon 1 anh. HR/CnB:
tien do, nhac nguoi chua gui, tai goi ZIP cho iVMS-4200. Logic o hr/face_photo/service.py.
no_cache bat buoc: HTML co anh + trang thai cua TUNG nguoi.
"""
import frappe

from ecentric_workspace.hr.face_photo import constants as C
from ecentric_workspace.hr.face_photo import service

no_cache = 1
sitemap = 0
MOUNT = '<aside class="ec-shell-mount" data-ec-shell="1" aria-label="Điều hướng eCentric"></aside>'


def _shell(context):
    from ecentric_workspace.shell import fallback as fb
    from ecentric_workspace.shell import server_nav
    mount = MOUNT
    try:
        mount = server_nav.rebuild_mount(MOUNT, C.ROUTE) or MOUNT
    except Exception:
        pass
    try:
        from ecentric_workspace.chat.gateway import chat_enabled
        chat = chat_enabled()
    except Exception:
        chat = False
    try:
        topbar = fb.render_topbar_inner(C.ROUTE, fb.make_detail("Ảnh khuôn mặt"), chat=chat)
    except Exception:
        topbar = ""
    context.km_shell_mount = mount
    context.km_topbar = topbar


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=" + C.ROUTE
        raise frappe.Redirect
    context.km = service.status(frappe.session.user)
    context.title = "Ảnh khuôn mặt"
    _shell(context)
    return context

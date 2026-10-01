# Copyright (c) 2026, eCentric and contributors
"""/tin-noi-bo/quan-ly (?tab=live|draft|expired) - HR xem / sua / go bai, kem luot xem."""
import frappe

from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import editor_service, pages, service

no_cache = 1
sitemap = 0


def get_context(context):
    pages.require_login(C.ROUTE_MANAGE)
    try:
        ctx = editor_service.manage_context(frappe.session.user, pages.arg("tab", "live"))
    except service.Forbidden:
        raise frappe.PermissionError("Chỉ HR được quản lý bài.")
    context.update(ctx)
    context.title = "Quản lý bài"
    pages.shell(context, C.ROUTE, detail=context.title)
    return context

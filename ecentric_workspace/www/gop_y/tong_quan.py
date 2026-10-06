# Copyright (c) 2026, eCentric and contributors
"""/gop-y/tong-quan - tong quan gop y cho BGD: so lieu thang, chu de, chu de nong (AI), qua han.

    ?thang=YYYY-MM (mac dinh thang nay)
"""
import frappe

from ecentric_workspace.feedback import constants as C
from ecentric_workspace.feedback import handler_service, pages

no_cache = 1
sitemap = 0


def get_context(context):
    pages.require_login(C.ROUTE_OVERVIEW)
    try:
        ctx = handler_service.overview(frappe.session.user, month=pages.arg("thang"))
    except handler_service.Forbidden:
        raise frappe.PermissionError("Chỉ Ban Giám đốc (phòng Management) xem được tổng quan góp ý.")
    context.update(ctx)
    context.title = "Tổng quan góp ý"
    pages.shell(context, detail=ctx["month_label"])
    return context

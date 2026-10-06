# Copyright (c) 2026, eCentric and contributors
"""/gop-y/xu-ly - hop xu ly gop y (phong Management - EC + quan tri).

    ?loc=can-xu-ly|qua-han|sap-het-han|da-dong|tat-ca   ?chu-de=<ma>   ?q=<chu>   ?gy=<ma dang mo>
Nguoi gui an danh hien "An danh" - trang nay khong co duong nao toi danh tinh.
"""
import frappe

from ecentric_workspace.feedback import constants as C
from ecentric_workspace.feedback import handler_service, pages

no_cache = 1
sitemap = 0


def get_context(context):
    pages.require_login(C.ROUTE_INBOX)
    try:
        ctx = handler_service.inbox(frappe.session.user, flt=pages.arg("loc", "can-xu-ly"),
                                    topic=pages.arg("chu-de"), q=pages.arg("q").strip()[:80],
                                    sel=pages.arg("gy").strip().upper())
    except handler_service.Forbidden:
        raise frappe.PermissionError("Chỉ Ban Giám đốc (phòng Management) xử lý góp ý.")
    context.update(ctx)
    context.title = "Hộp xử lý góp ý"
    pages.shell(context, detail=context.title)
    return context

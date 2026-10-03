# Copyright (c) 2026, eCentric and contributors
"""/gop-y/<ma> - mot gop y, goc nhin NGUOI GUI (luong trao doi, tien do, nhan them, "Chua on").

Nguoi xu ly mo link nay (tu chuong) -> chuyen sang hop xu ly voi gop y do. Nguoi khac va ma sai
-> CUNG 404 (khong cho do ma nao ton tai). Danh dau "da doc cap nhat" bang POST tu JS.
"""
import frappe

from ecentric_workspace.feedback import constants as C
from ecentric_workspace.feedback import pages, service

no_cache = 1
sitemap = 0


def get_context(context):
    code = pages.arg("code").strip().upper()
    pages.require_login("%s/%s" % (C.ROUTE, code))
    user = frappe.session.user
    try:
        ctx = service.detail(user, code)
    except (service.NotFound, service.Forbidden) as e:
        from ecentric_workspace.feedback import repository
        if isinstance(e, service.Forbidden) and service.is_handler(repository, user):
            pages.redirect("%s?gy=%s" % (C.ROUTE_INBOX, code))
        # Ma khong co va gop y cua nguoi khac tra CUNG mot loi: khong cho do ma nao ton tai.
        raise frappe.PageDoesNotExistError("Không tìm thấy góp ý này.")
    context.update(ctx)
    context.title = ctx["fb"]["title"]
    pages.shell(context, detail=code)
    return context

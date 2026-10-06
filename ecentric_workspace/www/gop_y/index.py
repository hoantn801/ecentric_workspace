# Copyright (c) 2026, eCentric and contributors
"""/gop-y - Gop y cong ty: gui gop y, gop y cua toi, bang chung (PO duyet mockup Ban 1, 04/10/2026).

Route: hooks.website_route_rules /gop-y -> gop_y (thu muc www khong duoc co gach ngang). Tham so:
    ?tab=gui|cua-toi|bang-chung
    ?sap-xep=nhieu-nhat|moi-nhat   (bang chung)
    ?loc=dang-xem|da-tra-loi|da-lam (bang chung)
"""
import frappe

from ecentric_workspace.feedback import constants as C
from ecentric_workspace.feedback import pages, service

no_cache = 1
sitemap = 0

_TITLES = {"gui": "Góp ý công ty", "cua-toi": "Góp ý của tôi", "bang-chung": "Bảng chung góp ý"}


def get_context(context):
    pages.require_login(C.ROUTE)
    try:
        ctx = service.index_page(frappe.session.user, tab=pages.arg("tab", "gui"), sort=pages.arg("sap-xep"),
                                 flt=pages.arg("loc"))
    except service.Forbidden:
        raise frappe.PermissionError("Chỉ nhân viên eCentric mới dùng được mục này.")
    context.update(ctx)
    context.title = _TITLES.get(ctx["tab"], "Góp ý công ty")
    pages.shell(context, detail=context.title if ctx["tab"] != "gui" else "")
    return context

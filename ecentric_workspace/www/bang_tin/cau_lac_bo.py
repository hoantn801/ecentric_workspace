# Copyright (c) 2026, eCentric and contributors
"""/bang-tin/cau-lac-bo - danh sach Cau lac bo (?loc=da-tham-gia|the-thao|so-thich) + de xuat CLB."""
import frappe

from ecentric_workspace.social import clubs, pages
from ecentric_workspace.social import constants as C

no_cache = 1
sitemap = 0


def get_context(context):
    pages.require_login(C.CLUBS_ROUTE)
    context.update(pages.guard(clubs.list_page, frappe.session.user, pages.arg("loc")))
    context.title = "Câu lạc bộ"
    pages.shell(context, detail="Câu lạc bộ")
    return context

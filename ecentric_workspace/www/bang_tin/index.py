# Copyright (c) 2026, eCentric and contributors
"""/bang-tin - Bang tin noi bo (mockup v2 "Bang tin + Cau lac bo", PO duyet 04/10/2026).

Route: hooks.website_route_rules /bang-tin -> bang_tin (thu muc www khong duoc co gach ngang).
    ?loc=tin-hr|loi-khen|phong-toi|clb-cua-toi|su-kien|cua-toi   loc
    ?truoc=<thoi diem>                                              trang sau (khong JS)
"""
import frappe

from ecentric_workspace.social import constants as C
from ecentric_workspace.social import feed, pages

no_cache = 1
sitemap = 0


def get_context(context):
    pages.require_login(C.ROUTE)
    context.update(pages.guard(feed.page, frappe.session.user, pages.arg("loc"), pages.arg("truoc")))
    context.title = "Bảng tin"
    pages.shell(context)
    return context

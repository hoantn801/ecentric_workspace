# Copyright (c) 2026, eCentric and contributors
"""/tai-lieu/quan-ly - danh muc tai lieu cho Ban ISO / truong BP (mockup B rut gon, PO duyet 04/10).

Tham so: ?loc=cho-toi|ra-soat|dang-soan|het-hieu-luc|tat-ca|phong  &phong=<Department>  &q=  &ma=<mo dong>
"""
import frappe

from ecentric_workspace.iso_docs import manage, pages

no_cache = 1
sitemap = 0


def get_context(context):
    pages.require_login(pages.ROUTE + "/quan-ly")
    context.update(manage.manage_page(frappe.session.user, flt=pages.arg("loc"), dept=pages.arg("phong"),
                                      q=pages.arg("q"), open_code=pages.arg("ma").strip().upper()))
    context.title = "Danh mục tài liệu"
    pages.shell(context, route=pages.ROUTE + "/quan-ly", detail="Danh mục")
    return context

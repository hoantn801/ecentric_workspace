# Copyright (c) 2026, eCentric and contributors
"""/tai-lieu - Thu vien tai lieu ISO cho nhan vien (mockup D, PO duyet 04/10/2026).

Route: hooks.website_route_rules /tai-lieu -> tai_lieu. Tham so:
    ?xem=phong-ban|viec|he-thong   cach xem
    ?phong=<ten Department>         phong dang chon (xem theo phong ban)
    ?q=<tu khoa>                    tim theo ma / ten / "dung khi"
"""
import frappe

from ecentric_workspace.iso_docs import library, pages

no_cache = 1
sitemap = 0


def get_context(context):
    pages.require_login(pages.ROUTE)
    context.update(library.library_page(frappe.session.user, view=pages.arg("xem", "phong-ban"),
                                        dept=pages.arg("phong"), q=pages.arg("q"),
                                        loai=pages.arg("loai")))
    context.title = "Thư viện tài liệu"
    context.can_manage = _can_manage()
    pages.shell(context)
    return context


def _can_manage():
    from ecentric_workspace.iso_docs import repository
    return repository.is_manager(frappe.session.user)

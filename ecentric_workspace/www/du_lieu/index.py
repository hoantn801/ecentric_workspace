# Copyright (c) 2026, eCentric and contributors
"""/du-lieu - Trung tam Du lieu: Yeu cau du lieu (KPI, loc, Danh sach | Gantt, tao yeu cau, popup).

Route: hooks.website_route_rules /du-lieu -> du_lieu (thu muc www khong duoc co gach ngang).
Tham so: ?ma=DR-2026-0001 (mo popup chi tiet), ?xem=gantt.
"""
import frappe

from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import pages, service

no_cache = 1
sitemap = 0


def get_context(context):
    return pages.render(context, C.ROUTE, lambda: service.index_page(
        frappe.session.user, code=pages.arg("ma"), view=pages.arg("xem")), "Trung tâm Dữ liệu")

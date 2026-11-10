# Copyright (c) 2026, eCentric and contributors
"""/du-lieu - Trung tam Du lieu: Yeu cau du lieu (KPI, loc, Danh sach | Gantt, tao yeu cau, popup).

Route: hooks.website_route_rules /du-lieu -> du_lieu (thu muc www khong duoc co gach ngang).
Tham so: ?ma=DR-2026-0001 (mo popup chi tiet), ?xem=gantt.
Dot 3: ?ma= nhan ca ma phieu Data Request cu (EC-DATA-...); ?id= la ten cu cua tham so - link
`<route the DATA_REQUEST>?id=EC-DATA-...` (thong bao, Viec cua toi) sau khi the tro /du-lieu.
"""
import frappe

from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import pages, service

no_cache = 1
sitemap = 0


def get_context(context):
    return pages.render(context, C.ROUTE, lambda: service.index_page(
        frappe.session.user, code=pages.arg("ma") or pages.arg("id"), view=pages.arg("xem")), "Trung tâm Dữ liệu")

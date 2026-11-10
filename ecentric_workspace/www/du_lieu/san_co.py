# Copyright (c) 2026, eCentric and contributors
"""/du-lieu/san-co - Data availability (dot 2): ma tran du lieu san co, do tuoi, de xuat data can crawl,
ke hoach bo sung (DA-), Thu vien bao cao (?xem=thu-vien; ?tu=DR-... mo form them tu yeu cau)."""
import frappe

from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import pages, service

no_cache = 1
sitemap = 0


def get_context(context):
    return pages.render(context, C.ROUTE_AVAIL, lambda: service.avail_page(
        frappe.session.user, view=pages.arg("xem"), prefill_ticket=pages.arg("tu")),
        "Data availability", detail="Data availability")

# Copyright (c) 2026, eCentric and contributors
"""/du-lieu/san-co - Data availability (dot 2). Dot 1: trang "Sap co" de menu / tab da dung cho."""
import frappe

from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import pages, service

no_cache = 1
sitemap = 0


def get_context(context):
    return pages.render(context, C.ROUTE_AVAIL, lambda: service.avail_page(frappe.session.user),
                        "Data availability", detail="Data availability")

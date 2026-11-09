# Copyright (c) 2026, eCentric and contributors
"""/du-lieu/quy-tac - Quy tac thoi han. Dot 1: bang quy tac dang ap dung (chi doc); sua + gui duyet +
nguoi duyet quy tac duyet / tu choi o dot 3."""
import frappe

from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import pages, service

no_cache = 1
sitemap = 0


def get_context(context):
    return pages.render(context, C.ROUTE_RULES, lambda: service.rules_page(frappe.session.user),
                        "Quy tắc thời hạn", detail="Quy tắc thời hạn")

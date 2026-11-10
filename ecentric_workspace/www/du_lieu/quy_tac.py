# Copyright (c) 2026, eCentric and contributors
"""/du-lieu/quy-tac - Quy tac thoi han: bang dang ap dung + de xuat moi (team Data sua, gui duyet) +
nguoi duyet quy tac Duyet / Tu choi + lich su phien ban (dot 3 - data_hub/rules_service.py).
Asset rieng ec_data_hub_rules.bundle.js / .css chi nap o trang nay."""
import frappe

from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import pages, service

no_cache = 1
sitemap = 0


def get_context(context):
    pages.render(context, C.ROUTE_RULES, lambda: service.rules_page(frappe.session.user),
                 "Quy tắc thời hạn", detail="Quy tắc thời hạn")
    context.edh_rules_js = pages.asset_url("rules_js")
    context.edh_rules_css = pages.asset_url("rules_css")
    return context

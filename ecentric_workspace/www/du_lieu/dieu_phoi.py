# Copyright (c) 2026, eCentric and contributors
"""/du-lieu/dieu-phoi - kanban dieu phoi cua team Data (Cho tiep nhan / Dang xu ly / Tam dung / Xong)."""
import frappe

from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import pages, service

no_cache = 1
sitemap = 0


def get_context(context):
    return pages.render(context, C.ROUTE_OPS, lambda: service.ops_page(frappe.session.user), "Điều phối",
                        detail="Điều phối")

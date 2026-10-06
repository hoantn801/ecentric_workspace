# Copyright (c) 2026, eCentric and contributors
"""/bang-tin/quan-ly - HR kiem duyet Bang tin (?tab=bao-cao|da-an|clb)."""
import frappe

from ecentric_workspace.social import moderation, pages
from ecentric_workspace.social import constants as C

no_cache = 1
sitemap = 0


def get_context(context):
    pages.require_login(C.MOD_ROUTE)
    context.update(pages.guard(moderation.page, frappe.session.user, pages.arg("tab")))
    context.title = "Kiểm duyệt Bảng tin"
    pages.shell(context, detail="Kiểm duyệt")
    return context

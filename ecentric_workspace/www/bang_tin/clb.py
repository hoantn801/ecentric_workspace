# Copyright (c) 2026, eCentric and contributors
"""/bang-tin/cau-lac-bo/<slug> - trang mot CLB (?tab=bai-viet|su-kien|anh|thanh-vien)."""
import frappe

from ecentric_workspace.social import clubs, pages
from ecentric_workspace.social import constants as C

no_cache = 1
sitemap = 0


def get_context(context):
    slug = pages.arg("slug").strip().lower()
    pages.require_login("%s/%s" % (C.CLUBS_ROUTE, slug))
    context.update(pages.guard(clubs.club_page, frappe.session.user, slug, pages.arg("tab"), pages.arg("truoc")))
    context.title = context.club["title"]
    pages.shell(context, detail=context.club["title"])
    return context

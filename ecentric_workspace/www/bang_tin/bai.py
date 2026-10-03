# Copyright (c) 2026, eCentric and contributors
"""/bang-tin/bai/<ten> - mot bai Bang tin (link tu chuong), binh luan mo san."""
import frappe

from ecentric_workspace.social import comments_subject, pages, service
from ecentric_workspace.social import constants as C

no_cache = 1
sitemap = 0


def get_context(context):
    name = pages.arg("name").strip()
    pages.require_login("%s/%s" % (C.POST_ROUTE, name))
    user = frappe.session.user
    card = pages.guard(service.post_view, user, name)
    context.items = [dict(card, type="post")]
    context.cm = comments_subject.view(user, name)
    context.title = "Bài trên Bảng tin"
    pages.shell(context, detail="Bài viết")
    return context

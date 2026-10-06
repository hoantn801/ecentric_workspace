# Copyright (c) 2026, eCentric and contributors
"""/tin-noi-bo/<slug> - mot bai Tin noi bo.

Quyen kiem phia server (internal_posts/permissions.py qua has_permission): Guest -> dang
nhap; nguoi ngoai pham vi bai / bai nhap ma khong phai HR -> 403 KHONG lo tieu de; slug sai
-> 404. Luot xem ghi bang POST tu JS sau khi trang tai (GET cua Frappe khong commit).
"""
import frappe

from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import pages, service

no_cache = 1
sitemap = 0


def get_context(context):
    slug = pages.arg("slug")
    pages.require_login("%s/%s" % (C.ROUTE, slug))
    try:
        post = service.post_page(frappe.session.user, slug)
    except service.NotFound:
        raise frappe.PageDoesNotExistError("Không tìm thấy bài này.")
    except service.Forbidden:
        raise frappe.PermissionError("Bài này không dành cho bạn.")
    context.post = post
    context.title = post["title"]
    pages.shell(context, C.ROUTE, detail=post["title"])
    return context

# Copyright (c) 2026, eCentric and contributors
"""/tin-noi-bo - danh sach Tin noi bo (huong "Chuyen muc", PO duyet mockup v5 01/10/2026).

Route: hooks.website_route_rules /tin-noi-bo -> tin_noi_bo (thu muc www khong duoc co gach
ngang vi Frappe import tep .py canh template theo duong dan). Tham so:
    ?chuyen-muc=<ma>   mot chuyen muc (/huong-dan chuyen huong ve ?chuyen-muc=huong-dan)
    ?chua-xem=1        bai nguoi xem chua mo
    ?q=<chu>           tim theo tieu de
    ?trang=<n>         phan trang (che do loc)
"""
import frappe

from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import pages, service

no_cache = 1
sitemap = 0


def get_context(context):
    pages.require_login(C.ROUTE)
    ctx = service.list_page(frappe.session.user, category=pages.arg("chuyen-muc"),
                            unseen=pages.arg("chua-xem") == "1", q=pages.arg("q"), page=pages.arg("trang", "1") or 1)
    context.update(ctx)
    cur = ctx.get("category")
    if cur:
        context.title = cur["name"]
    elif ctx.get("unseen"):
        context.title = "Bài bạn chưa xem"
    elif ctx.get("q"):
        context.title = "Tìm: %s" % ctx["q"]
    else:
        context.title = "Tin nội bộ"
    pages.shell(context, C.ROUTE, detail=(context.title if context.title != "Tin nội bộ" else ""))
    return context

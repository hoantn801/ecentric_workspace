# Copyright (c) 2026, eCentric and contributors
"""/tin-noi-bo/viet-bai (?bai=<ten> de sua) - HR soan bai ngay tren ERP (PO duyet mockup v5).

Chi EDITOR_ROLES; nguoi khac -> 403. Gia tri ban dau cua moi o do server ve san; JS chi
gan hanh vi (dinh dang, tai anh, AI anh bia, luu / dang).
"""
import frappe

from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import editor_service, pages, service

no_cache = 1
sitemap = 0


def get_context(context):
    name = pages.arg("bai")
    pages.require_login(C.ROUTE_COMPOSE + ("?bai=" + name if name else ""))
    try:
        ctx = editor_service.compose_context(frappe.session.user, name or None)
    except service.Forbidden:
        raise frappe.PermissionError("Chỉ HR được viết bài.")
    except service.NotFound:
        raise frappe.PageDoesNotExistError("Không tìm thấy bài này.")
    context.update(ctx)
    context.title = "Sửa bài" if ctx.get("post") else "Viết bài mới"
    context.ip_data_json = frappe.as_json({
        "post": ctx.get("post"), "departments": ctx["departments"], "employee_lfts": ctx["employee_lfts"],
        "company_size": ctx["company_size"], "ai_limit": ctx["ai_limit"], "ai_used": ctx["ai_used"],
        "ai_enabled": ctx["ai_enabled"], "colors": ctx["colors"],
        "categories": ctx["categories"],
    }, indent=None).replace("</", "<\\/")
    pages.shell(context, C.ROUTE, detail=context.title)
    context.ip_editor_js = pages.asset_url("editor")
    return context

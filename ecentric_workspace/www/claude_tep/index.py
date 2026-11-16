# Copyright (c) 2026, eCentric and contributors
"""/claude_tep - trang thả tệp cho Claude (cổng MCP, ecentric_workspace/claude_mcp/files.py).

Vì sao có trang này: tệp người dùng thả vào khung chat Claude không đi được sang ERP qua MCP.
Trang tải tệp lên như ô "Tệp đính kèm" của form tạo phiếu: upload_file, is_private=1, KHÔNG kèm
doctype/docname -> tệp riêng tư của chính người tải. Claude thấy tệp qua list_my_uploads và gắn
vào phiếu khi lưu nháp. Không cần route rule trong hooks.py (tên thư mục không có gạch ngang).
"""
import frappe

no_cache = 1
sitemap = 0


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/claude_tep"
        raise frappe.Redirect
    from frappe.utils import add_to_date, now_datetime
    from frappe.sessions import get_csrf_token

    context.no_breadcrumbs = True
    context.title = "Gửi tệp cho Claude"
    context.csrf = get_csrf_token()
    context.recent = frappe.get_all(
        "File",
        filters={"owner": frappe.session.user, "is_folder": 0, "attached_to_name": ["is", "not set"],
                 "creation": [">=", add_to_date(now_datetime(), hours=-24)]},
        fields=["file_name", "creation"], order_by="creation desc", limit_page_length=50)
    return context

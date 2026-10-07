# Copyright (c) 2026, eCentric and contributors
"""p274_create_ai_usage_page: tao Web Page /ai-usage (Thong ke dung AI) tu repo, chay mot lan
luc migrate. Dung chung page_sync.sync() voi endpoint dong bo tay."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_usage import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = page_sync.sync()
        frappe.logger("ai_tools").info("p274_create_ai_usage_page: %s" % (res or {}))
    except Exception:
        frappe.log_error(title="p274_create_ai_usage_page")

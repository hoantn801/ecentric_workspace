# Copyright (c) 2026, eCentric and contributors
"""p276_backfill_ai_usage_log: dung lai so lieu dung AI truoc 07/10 tu dau vet co san
(AI dien phieu, tom tat cong ty, cham bao cao tuan, anh bia). Xem platform/ai/usage_backfill.py.
Chay mot lan; loi thi ghi Error Log, khong chan migrate."""
import frappe

from ecentric_workspace.platform.ai import usage_backfill


def execute():
    if not frappe.db.exists("DocType", usage_backfill.DOCTYPE):
        return
    try:
        frappe.reload_doc("ecentric_workspace", "doctype", "ec_ai_usage_log")
        res = usage_backfill.run()
        frappe.db.commit()
        frappe.logger("ai_tools").info("p276_backfill_ai_usage_log: %s" % (res or {}))
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="p276_backfill_ai_usage_log")

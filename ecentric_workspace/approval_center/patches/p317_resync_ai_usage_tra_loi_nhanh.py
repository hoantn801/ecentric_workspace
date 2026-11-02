# Copyright (c) 2026, eCentric and contributors
"""p317_resync_ai_usage_tra_loi_nhanh (03/11/2026, QA UX mang AI): dong bo lai Web Page /ai-usage.
Khoi "Tra loi nhanh" (ai dung / dung gi / co on khong / ton bao nhieu), bang thanh the tren dien
thoai, danh sach nguoi gon 10 dong, tim kiem khong ve lai ca trang, sap xep bang ban phim, trang
thai rong / loi 403 co huong di tiep. Hop dong usage_api.summary giu nguyen.
Dung chung page_sync.sync() voi endpoint dong bo tay."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_usage import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = page_sync.sync()
        frappe.logger("ai_tools").info("p317_resync_ai_usage_tra_loi_nhanh: %s" % (res or {}))
    except Exception:
        frappe.log_error(title="p317_resync_ai_usage_tra_loi_nhanh")

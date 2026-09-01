# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub sau khi Việt hoá giá trị hiển thị (shared/vi_display).

Phần dịch chạy ở server nên bảng + popup có ngay sau deploy; patch này chỉ để chắc chắn
HTML hub khớp repo (page_sync idempotent, không đổi gì thì trả unchanged)."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p125 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p125 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p125 resync failed")

# Copyright (c) 2026, eCentric and contributors
"""p578_tai_san_qc_giao_dien: dong bo lai 7 trang tai san sau dot QC giao dien 27/11/2026 (Hoan bao
bam dong o Danh sach thiet bi khong mo chi tiet; tieu de Cap phat / Kiem ke ghi sai "Tong quan").
Nguon tai_san/pages/*, cach ghi xem tai_san/pages/sync.py."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.tai_san.pages import sync
        frappe.logger("approval_center").info("p578 tai_san: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p578_tai_san_qc_giao_dien")

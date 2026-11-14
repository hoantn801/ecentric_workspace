# Copyright (c) 2026, eCentric and contributors
"""p377_dao_tao_ket_qua_giai: dong bo lai 7 trang Dao tao + Quiz (Hoan 13/11/2026).

Man Ve dich co danh sach nhan giai (email, phong ban) + tai CSV; trang Quiz co ket qua phong da ket thuc. HTML chi doi ?v=."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p377 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p377_dao_tao_ket_qua_giai")

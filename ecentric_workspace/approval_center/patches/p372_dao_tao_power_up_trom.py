# Copyright (c) 2026, eCentric and contributors
"""p372_dao_tao_power_up_trom: dong bo lai 7 trang Dao tao + Quiz (Hoan 13/11/2026).

Them 2 power-up: "Danh cap" (lay 100-300 diem cua nguoi ngay tren luc khoa cau) va "Khien chan"
(tu chan 1 lan bi danh cap); may chieu + dien thoai bao ten vu danh cap. HTML chi doi ?v=."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p372 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p372_dao_tao_power_up_trom")

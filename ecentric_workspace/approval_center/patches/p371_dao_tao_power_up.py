# Copyright (c) 2026, eCentric and contributors
"""p371_dao_tao_power_up: dong bo lai 7 trang Dao tao + Quiz (Hoan 13/11/2026).

Power-up moi 5 cau (chon bo tui, tu bam dung truoc khi tra loi) + bao "x2 cau cuoi" tren may chieu
va dien thoai; cong tac "Power-up moi 5 cau" trong Luat choi. HTML chi doi ?v=. Khong dung trang khac."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p371 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p371_dao_tao_power_up")

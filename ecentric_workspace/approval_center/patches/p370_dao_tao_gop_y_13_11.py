# Copyright (c) 2026, eCentric and contributors
"""p370_dao_tao_gop_y_13_11: dong bo lai 7 trang Dao tao + Quiz (gop y Hoan 13/11/2026 truoc buoi hoc).

Nhan vat ve lai, o nhap ten tren dien thoai het chu trang, bang xep hang may chieu de doc hon, chon
nhieu dap an hien dau tick, nut "Cong bo" thay "Khoa cau", nhac YouTube luc choi, cong tac "dien
thoai cung thu tu + mau voi man chieu". HTML chi doi ?v=. Khong dung trang nao khac."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p370 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p370_dao_tao_gop_y_13_11")

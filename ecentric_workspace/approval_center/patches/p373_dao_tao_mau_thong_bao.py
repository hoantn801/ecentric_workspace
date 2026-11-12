# Copyright (c) 2026, eCentric and contributors
"""p373_dao_tao_mau_thong_bao: dong bo lai 7 trang Dao tao + Quiz (Hoan 13/11/2026).

Thong bao loi (toast do) nam ngoai #ec-dt nen bien --bad khong co -> chu trang tren nen trang.
Doi sang mau co dinh. HTML chi doi ?v=. Khong dung trang nao khac."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p373 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p373_dao_tao_mau_thong_bao")

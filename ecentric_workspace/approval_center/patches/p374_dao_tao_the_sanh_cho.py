# Copyright (c) 2026, eCentric and contributors
"""p374_dao_tao_the_sanh_cho: dong bo lai 7 trang Dao tao + Quiz (Hoan 13/11/2026).

The nguoi choi o sanh cho may chieu to hon, email khong tran ra ngoai the. HTML chi doi ?v=."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p374 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p374_dao_tao_the_sanh_cho")

# Copyright (c) 2026, eCentric and contributors
"""p375_dao_tao_sanh_cap_nhat_ten: dong bo lai 7 trang Dao tao + Quiz (Hoan 13/11/2026).

Sanh cho may chieu ve lai khi nguoi choi doi ten / nhan vat. HTML chi doi ?v=."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p375 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p375_dao_tao_sanh_cap_nhat_ten")

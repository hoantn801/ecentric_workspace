# Copyright (c) 2026, eCentric and contributors
"""p376_dao_tao_qc_truoc_buoi: dong bo lai 7 trang Dao tao + Quiz (Hoan 13/11/2026).

Sua sau 3 vong QC truoc buoi hoc: may chieu vua 1 man hinh, bang/buc trao giai, chu to hon, power-up an toan hon. HTML chi doi ?v=."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p376 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p376_dao_tao_qc_truoc_buoi")

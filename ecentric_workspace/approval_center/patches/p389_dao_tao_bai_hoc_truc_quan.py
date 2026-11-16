# Copyright (c) 2026, eCentric and contributors
"""p389_dao_tao_bai_hoc_truc_quan: dong bo lai 7 trang Dao tao + Quiz (Hoan 15/11/2026).

Bai hoc hien noi dung co dinh dang (ec_dt_rich.js: muc luc, the, so lieu, so sanh, anh, video trong
bai); trinh soan bai co nut Chen anh / video + Xem truoc. Trang bai hoc + quan ly them 1 the script,
cac trang con lai chi doi ?v= (ec_dt.css)."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p389 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p389_dao_tao_bai_hoc_truc_quan")

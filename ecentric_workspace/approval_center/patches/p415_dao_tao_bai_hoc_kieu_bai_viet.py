# Copyright (c) 2026, eCentric and contributors
"""p415_dao_tao_bai_hoc_kieu_bai_viet: dong bo lai 7 trang Dao tao + Quiz (Hoan 18/11/2026).

Trang bai hoc doi sang kieu bai viet nhu Tin noi bo (banner toi + the bai viet + cot phai muc luc,
phan thuong) va danh sach viec co o tich. HTML chi doi ?v= (ec_dt.css, ec_dt_rich.js, ec_dt_lesson.js,
ec_dt_admin.js)."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p415 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p415_dao_tao_bai_hoc_kieu_bai_viet")

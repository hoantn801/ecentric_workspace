# Copyright (c) 2026, eCentric and contributors
"""p369_dao_tao_nhac_may_chieu: dong bo lai 7 trang Dao tao + Quiz (Hoan 13/11/2026).

Man chieu /quiz/chieu co them nhac (ec_dt_music.js): bai YouTube luc cho vao phong, nhac nen
khong loi tu tao luc choi; tieu de tren nen tim doi sang trang cho de doc. HTML chi doi the
script + ?v=. Khong dung trang nao khac."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p369 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p369_dao_tao_nhac_may_chieu")

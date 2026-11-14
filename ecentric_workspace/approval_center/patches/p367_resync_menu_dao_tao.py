# Copyright (c) 2026, eCentric and contributors
"""p367_resync_menu_dao_tao: menu "Dao tao" het "Sap co" -> /dao-tao, them "Quiz truc tiep"
(/quiz) o nhom Tai nguyen + rail "Cong ty" (Hoan 12/11/2026).

Menu song do server ve luc render (shell/nav.py) nen doi ngay khi deploy; patch nay chi
dong bo VO SHELL TINH (fallback) dut san trong 3 trang co nhom "Tai nguyen": trang chu,
/viec-cua-toi, /tong-quan. Moi trang qua page_sync rieng (trang chu co khoa lech). Tu bat loi."""
import frappe


def _one(label, fn):
    try:
        res = fn() or {}
        frappe.logger("approval_center").info("p367 %s: %s" % (label, res))
        if isinstance(res, dict) and res.get("action") == "refused":
            frappe.log_error("p367_resync_menu_dao_tao: %s refused (live drift): %s" % (label, res),
                             "p367_resync_menu_dao_tao")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p367_resync_menu_dao_tao %s failed" % label)


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.action_center.pages.my_work import page_sync as my_work
    from ecentric_workspace.hr.pages.tong_quan import page_sync as tong_quan
    from ecentric_workspace.legacy_pages.home import page_sync
    _one("home", lambda: page_sync.sync())
    _one("viec-cua-toi", my_work.sync)
    _one("tong-quan", tong_quan.sync)

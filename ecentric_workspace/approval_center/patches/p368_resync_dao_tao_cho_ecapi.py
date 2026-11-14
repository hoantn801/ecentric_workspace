# Copyright (c) 2026, eCentric and contributors
"""p368_resync_dao_tao_cho_ecapi: dong bo lai 7 trang Dao tao + Quiz (Hoan 12/11/2026).

Sau deploy p366, trang bao "Trang chua tai xong" vi script trang chay truoc khi bundle chung
(window.ecApi) nap xong o cuoi body. ec_dt_core.js nay cho ecApi san sang roi moi goi API;
HTML chi doi ?v= de trinh duyet lay file moi. Khong dung trang nao khac."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.dao_tao.pages import sync
        frappe.logger("approval_center").info("p368 dao_tao: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p368_resync_dao_tao_cho_ecapi")

# Copyright (c) 2026, eCentric and contributors
"""p253_khao_sat_hop_qua_form: hop qua tren dau form + xem so da chon (Hoan 02/10/2026).

Popover hop qua chuyen sang position:fixed (khong bi khung cuon cat); them hop qua o dau form lam
khao sat; tab Ket qua co nut "Xem cac so da chon". Doi asset trong
public/surveys/ -> doi ?v= trong 4 trang khao sat -> resync 4 trang (repo so huu toan bo byte). Khong dung trang nao khac."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.surveys.pages import sync
        frappe.logger("approval_center").info("p253 surveys: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p253_khao_sat_hop_qua_form")

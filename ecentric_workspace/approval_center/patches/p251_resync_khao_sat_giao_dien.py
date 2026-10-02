# Copyright (c) 2026, eCentric and contributors
"""p251_resync_khao_sat_giao_dien: sua giao dien khao sat sau lan len production 01/10/2026.

CSS cua Frappe (website.bundle) de len trang khao sat: `.icon { margin:0 auto }` lam nut Quay lai
va cac nut cuoi the cau hoi lech; `input[type=checkbox] { width:...!important }` lam cong tac bat/tat
co lai, nut tron de len chu. Sua o public/surveys/ec_survey.css -> doi ?v= trong 4 trang khao sat
-> resync 4 trang (repo so huu toan bo byte). Khong dung trang nao khac."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.surveys.pages import sync
        frappe.logger("approval_center").info("p251 surveys: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p251_resync_khao_sat_giao_dien")

# Copyright (c) 2026, eCentric and contributors
"""Seed mau khao sat ca nhan TAM (6 moc thu viec / thuc tap + khao sat nghi viec) - 23/11/2026.

Chi tao mau con thieu (theo ma_mau), khong sua mau HR da chinh. Khong gui thong bao, khong giao
cho ai (giao la viec cua job 09:00). Khong nem loi (migrate gay = rollback ca ban deploy)."""
import frappe


def execute():
    try:
        if not frappe.db.has_column("EC Survey", "ma_mau"):
            frappe.reload_doc("surveys", "doctype", "ec_survey")
        from ecentric_workspace.surveys.application import mau_tam
        from ecentric_workspace.surveys.infrastructure import repository as repo
        made = mau_tam.dam_bao_mau_tam(repo)
        frappe.db.commit()
        frappe.log_error(title="surveys p002 mau khao sat ca nhan", message="da tao: %s" % made)
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "surveys p002 mau khao sat ca nhan THAT BAI")

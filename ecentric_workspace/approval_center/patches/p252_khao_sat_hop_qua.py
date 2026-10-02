# Copyright (c) 2026, eCentric and contributors
"""p252_khao_sat_hop_qua: hop qua goc the khao sat + nhac nguoi chua lam ra ca Teams (Hoan 02/10/2026).

Trang /khao-sat: dai chu "So may man: ..." bi cat -> hop qua goc tren phai the, tro chuot / cham
hien danh sach qua. Hop thoai "Nhac nguoi chua lam" doi chu (chuong ERP + Teams). Doi asset trong
public/surveys/ -> doi ?v= trong 4 trang khao sat -> resync 4 trang (repo so huu toan bo byte). Khong dung trang nao khac."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.surveys.pages import sync
        frappe.logger("approval_center").info("p251 surveys: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p252_khao_sat_hop_qua")

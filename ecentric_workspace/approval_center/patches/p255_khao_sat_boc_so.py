# Copyright (c) 2026, eCentric and contributors
"""p255_khao_sat_boc_so: nop phieu chua chon so -> may boc giup + nhac chon so (Hoan 02/10/2026).

Tab Ket qua: danh sach "da nop - chua chon so" + nut "Nhac chon so"; trang chon so them dong
"Quen chon thi toi gio may boc giup". Doi asset trong
public/surveys/ -> doi ?v= trong 4 trang khao sat -> resync 4 trang (repo so huu toan bo byte). Khong dung trang nao khac."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.surveys.pages import sync
        frappe.logger("approval_center").info("p255 surveys: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p255_khao_sat_boc_so")

# Copyright (c) 2026, eCentric and contributors
"""p307_ai_live_schedule_settings_init (fix10g): dat gia tri mac dinh cho EC AI Live Schedule Settings (Single moi):
giu gio cu khi sap len song 15 phut; TAT gui lenh tai lich ngay khi phat hanh cho toi khi app eC Live hieu lenh
refresh_config (hop dong 1.0.21 chua co lenh nay - app se bao 'Lenh khong ho tro'); bat lai o Desk khi app san sang. Single chua luu lan nao thi o Check / Int
doc ra 0 chu khong phai mac dinh cua DocType. Chay lai nhieu lan khong sao (chi dat khi chua co)."""
import frappe

DT = "EC AI Live Schedule Settings"


def execute():
    if not frappe.db.exists("DocType", DT):
        return
    have = {r[0] for r in frappe.db.sql("select field from `tabSingles` where doctype=%s", (DT,))}
    vals = {k: v for k, v in (("lock_minutes", 15), ("refresh_on_publish", 0), ("current_version", 0)) if k not in have}
    if vals:
        frappe.db.set_single_value(DT, vals)

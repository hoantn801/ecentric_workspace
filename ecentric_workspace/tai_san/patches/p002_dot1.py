# Copyright (c) 2026, eCentric and contributors
"""p002: dot 1-3 Quan ly tai san - field moi tren Asset (ec_reserved_for, ec_end_date) va kiem tra
nen dot 0 (p001) da du.

DocType moi (EC Asset Event / Repair / Monthly / Count / Count Item) do migrate tu dong bo tu JSON
cua module, khong can patch. Patch nay chi:
    1. Chay lai cac buoc idempotent cua p001: tao Custom Field con thieu (gom 2 field moi), dam bao
       o trang thai co du 9 gia tri, role EC Asset Manager, mac dinh Asset Category.
    2. Moi Asset chua co ec_condition / ec_ownership -> Good / Owned (54 may truoc dot 0 de trong).
Khong doi trang thai, nguoi giu, gia cua may nao. Chay lai bao nhieu lan cung duoc.
"""
import frappe

from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san.patches import p001_setup as P1

TITLE = "tai_san p002 dot1"


def execute():
    if not frappe.db.exists("DocType", C.ASSET):
        return
    P1.execute()
    try:
        for field, value in (("ec_condition", C.COND_GOOD), ("ec_ownership", C.OWN_COMPANY)):
            if frappe.db.has_column(C.ASSET, field):
                frappe.db.sql("update `tabAsset` set `%s`=%%s where coalesce(`%s`, '')=''" % (field, field),
                              (value,))
    except Exception:
        frappe.log_error(title="%s: defaults" % TITLE)

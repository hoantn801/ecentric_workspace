# Copyright (c) 2026, eCentric and contributors
"""p008: tinh lai cay bao cao Employee (lft/rgt) theo reports_to hien co (05/11/2026, Hoan duyet).

CASE: chi Phuong (Phuong Nguyen Thi, HR-EMP-00015) xem lich cong nhom thi THIEU ban Trinh Minh
Thu (HR-EMP-00074), du reports_to cua Thu dung la HR-EMP-00015 tu 08/09. Danh sach nhom
(ec_hr_team_members, ec_hr_attendance_data member, duyet theo cap tren gian tiep...) doc theo
cay nested set lft/rgt chu khong doc reports_to: Thu 167-168 nam NGOAI khoang cua chi Phuong
158-167. Kiem toan cong ty 05/11: 2/105 nguoi lech (them Gia Diep Tu HR-EMP-00050).

Chi tinh lai lft/rgt - KHONG doi ai bao cao cho ai. Rebuild Tree chuan cua Frappe (giong nut
"Rebuild Tree" o tree view), cung cach pm p019 da lam voi Task. Chay lai bao nhieu lan cung vay.
FAIL-SAFE: loi -> Error Log, khong chan migrate.
"""
import frappe

TITLE = "p008 rebuild employee tree"


def _lech():
    rows = frappe.db.sql(
        "select c.name from `tabEmployee` c join `tabEmployee` p on p.name = c.reports_to"
        " where not (c.lft > p.lft and c.rgt < p.rgt)")
    return [r[0] for r in rows]


def execute():
    try:
        truoc = _lech()
        from frappe.utils.nestedset import rebuild_tree
        try:
            rebuild_tree("Employee", "reports_to")
        except TypeError:
            rebuild_tree("Employee")
        frappe.log_error(title=TITLE, message="lech truoc=%s sau=%s" % (truoc, _lech()))
    except Exception:
        frappe.log_error(title=TITLE, message=frappe.get_traceback())

# Copyright (c) 2026, eCentric and contributors
"""Go quyen `export` cua Role `EC Finance` tren `EC Payment Request` (15/09, Hoan chot).

p190 cap quyen DOC cho Role EC Finance. Chinh docstring cua no ghi ro "export/report KHONG
cap: khong bay san mot duong keo ca bang ra ngoai" - nhung ket qua tren production la
`read=1, export=1`. Ly do: `frappe.permissions.add_permission()` tao dong Custom DocPerm moi
voi MAC DINH cua Frappe, trong do `export` da bat san; p190 chi dat `read=1` roi dinh ninh
phan con lai bang 0, khong kiem lai.

KHOANG CACH GIUA "code noi" va "code lam" - do moi la thu dang sua o day. Bay gio dat tuong
minh `export=0` thay vi tin vao mac dinh.

Muc do: 7 nguoi phong Finance VON DA doc duoc moi phieu chi (do la quyen read Hoan duyet).
`export` khong cho ho thay gi moi, nhung bien viec mang CA BANG ra ngoai - ca so tien lan ten
nguoi thu huong - thanh mot cu bam. Khac biet nam o "xem trong app" voi "mang di hang loat".

KHONG BAO GIO nem loi: patch chay trong migrate (p116). Idempotent.
"""
import frappe
from frappe.permissions import update_permission_property

ROLE = "EC Finance"
DOCTYPE = "EC Payment Request"
#: Dat TUONG MINH ve 0. Khong dua vao mac dinh cua Frappe - chinh cho do lam p190 lech.
GO_BO = ("export", "report", "print", "email", "share")


def execute():
    try:
        if not frappe.db.exists("Custom DocPerm", {"parent": DOCTYPE, "role": ROLE}):
            frappe.log_error("chua co Custom DocPerm cho %s/%s -> bo qua" % (DOCTYPE, ROLE),
                             "p198 finance no export")
            return
        for ptype in GO_BO:
            update_permission_property(DOCTYPE, ROLE, 0, ptype, 0, validate=False)
        frappe.clear_cache(doctype=DOCTYPE)
        con = frappe.db.get_value("Custom DocPerm", {"parent": DOCTYPE, "role": ROLE},
                                  ["read", "write", "export"], as_dict=True)
        frappe.log_error("sau khi go: %s" % (con,), "p198 finance no export")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p198 finance no export THAT BAI")

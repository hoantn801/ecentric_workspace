# Copyright (c) 2026, eCentric and contributors
"""p003_dot4 - Quan ly tai san dot 4 (Hoan 26/11/2026).

* Trang cu /it-asset-management-system: GO PUBLISH (published=0), khong xoa - noi dung con nguyen
  de doi chieu; nguoi vao link cu duoc hooks.website_redirects dua sang /tai-san.
* DocType cu "IT Asset Management System" (2 ban ghi) KHONG dung toi: con phai PO xem 2 ban ghi do.
Idempotent: chay lai khong doi gi them.
"""
import frappe

OLD_ROUTE = "it-asset-management-system"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    for name in frappe.get_all("Web Page", filters={"route": OLD_ROUTE, "published": 1}, pluck="name"):
        frappe.db.set_value("Web Page", name, "published", 0, update_modified=False)
        frappe.logger("tai_san").info("p003: go publish Web Page %s (/%s)" % (name, OLD_ROUTE))

# Copyright (c) 2026, eCentric and contributors
"""EC License Event: nhat ky (app xin / cap / cho / khoa / bao ve + thao tac cua nguoi). KHONG BAO GIO ghi token / khoa."""
from ecentric_workspace.ai_tools.features.ai_live import license_constants as L

_FIELDS = ["name", "machine", "product", "kind", "ip", "user", "detail", "at"]


class LicenseEventRepository:
    def add(self, machine, product, kind, ip="", user="", detail=""):
        import frappe
        frappe.get_doc({"doctype": L.EVENT, "machine": machine or None, "product": product or "", "kind": kind,
                        "ip": (ip or "")[:64], "user": (user or "")[:140], "detail": (detail or "")[:1000],
                        "at": frappe.utils.now_datetime()}).insert(ignore_permissions=True)

    def for_machine(self, machine, limit=L.DETAIL_EVENTS):
        import frappe
        return frappe.get_all(L.EVENT, filters={"machine": machine}, fields=_FIELDS, order_by="at desc, creation desc",
                              limit_page_length=limit)

    def search(self, f, page):
        """f: {machine, product, kind, date_from, date_to} (da kiem o service)."""
        import frappe
        flt = {k: f[k] for k in ("machine", "product", "kind") if f.get(k)}
        if f.get("date_from") and f.get("date_to"):
            flt["at"] = ["between", [f["date_from"] + " 00:00:00", f["date_to"] + " 23:59:59"]]
        elif f.get("date_from"):
            flt["at"] = [">=", f["date_from"] + " 00:00:00"]
        elif f.get("date_to"):
            flt["at"] = ["<=", f["date_to"] + " 23:59:59"]
        rows = frappe.get_all(L.EVENT, filters=flt, fields=_FIELDS, order_by="at desc, creation desc",
                              limit_start=page * L.PAGE_SIZE, limit_page_length=L.PAGE_SIZE + 1)
        return rows[:L.PAGE_SIZE], len(rows) > L.PAGE_SIZE

    def purge_checkins(self, before):
        import frappe
        frappe.db.delete(L.EVENT, {"kind": L.Kind.CHECKIN, "at": ["<", before]})

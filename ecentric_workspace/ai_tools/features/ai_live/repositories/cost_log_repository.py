# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Cost Log. Moi dong = (may, brand, phien, ngay); app gui so luy ke nen ghi de."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C


class CostLogRepository:
    def upsert(self, key, row):
        import frappe
        if frappe.db.exists(C.COST_LOG, key):
            doc = frappe.get_doc(C.COST_LOG, key)
            for k, v in row.items():
                doc.set(k, v)
            doc.save(ignore_permissions=True)
        else:
            frappe.get_doc(dict(row, doctype=C.COST_LOG, log_key=key)).insert(ignore_permissions=True)

    def day_total(self, brand, date):
        import frappe
        r = frappe.db.sql("select coalesce(sum(usd), 0) from `tabEC AI Live Cost Log` where brand=%s and date=%s",
                          (brand, date))
        return float(r[0][0] if r else 0)

    def summary(self, since, brand=None):
        """[{brand, date, usd, sessions, machines}] tu ngay since (YYYY-MM-DD)."""
        import frappe
        cond, args = "date >= %s", [since]
        if brand:
            cond += " and brand = %s"
            args.append(brand)
        rows = frappe.db.sql("select brand, date, sum(usd) usd, count(distinct session) sessions, "
                             "count(distinct machine) machines from `tabEC AI Live Cost Log` where " + cond +
                             " group by brand, date order by date desc, brand asc", tuple(args), as_dict=True)
        return [{"brand": r.brand, "date": str(r.date), "usd": round(float(r.usd or 0), 4),
                 "sessions": int(r.sessions or 0), "machines": int(r.machines or 0)} for r in rows]

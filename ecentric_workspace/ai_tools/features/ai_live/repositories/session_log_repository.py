# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Session Log: 1 dong = tong ket 1 lan chay cua 1 phien live (ghi de theo khoa may+live+ma phien)."""
import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C

FIELDS = ["name", "log_key", "live", "machine", "brand", "app_session", "started_ts", "ended_ts", "duration_s",
          "comments", "answered", "greeted", "faq", "ai", "cost_usd", "alerts", "reason"]


def _row(r):
    out = {k: r.get(k) for k in FIELDS}
    for k in ("started_ts", "ended_ts", "cost_usd"):
        out[k] = float(out[k] or 0)
    for k in ("duration_s", "comments", "answered", "greeted", "faq", "ai", "alerts"):
        out[k] = int(out[k] or 0)
    return out


def _dt(ts):
    import frappe
    utc = datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc).replace(tzinfo=None)
    return frappe.utils.convert_utc_to_system_timezone(utc).replace(tzinfo=None)


class SessionLogRepository:
    def upsert(self, key, row):
        import frappe
        vals = {"live": row["live"], "machine": row["machine"], "brand": row.get("brand") or "",
                "app_session": row["session"], "started_ts": row["started_ts"], "ended_ts": row["ended_ts"],
                "started_at": _dt(row["started_ts"]), "duration_s": row["duration_s"], "cost_usd": row["cost_usd"],
                "alerts": row["alerts"], "reason": row["reason"], **row["counters"]}
        name = frappe.db.get_value(C.SESSION_LOG, {"log_key": key}, "name")
        if name:
            frappe.db.set_value(C.SESSION_LOG, name, vals, update_modified=False)
            return name
        doc = frappe.get_doc(dict(vals, doctype=C.SESSION_LOG, log_key=key))
        doc.insert(ignore_permissions=True)
        return doc.name

    def list(self, since_ts, live=None, brand=None, limit=500):
        import frappe
        filters = {"started_ts": [">=", since_ts]}
        if live:
            filters["live"] = live
        if brand:
            filters["brand"] = brand
        rows = frappe.get_all(C.SESSION_LOG, filters=filters, fields=FIELDS, order_by="started_ts desc",
                              limit_page_length=limit)
        return [_row(r) for r in rows]

    def purge(self, before_ts):
        import frappe
        frappe.db.delete(C.SESSION_LOG, {"started_ts": ["<", before_ts]})

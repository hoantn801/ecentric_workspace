# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Incident (fix10h): su co may im lang / bao dong app nho ERP gui ho. Ghi bang set_value
(khong tao Version moi lan nhac lai)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C

_TS = ("opened_ts", "first_sent_ts", "last_sent_ts", "acked_ts", "escalated_ts", "resolved_ts", "missing_since_ts")
FIELDS = ["name", "incident_key", "kind", "status", "level", "machine", "live", "brand", "code", "title", "text",
          "sent_count", "acked_by", "ack_note", "resolve_text"] + list(_TS)
#: truong epoch -> Datetime de xem tren Desk
_DT = {"opened_ts": "opened_at", "acked_ts": "acked_at", "resolved_ts": "resolved_at"}


def _row(r):
    out = {k: r.get(k) for k in FIELDS}
    for k in _TS:
        out[k] = float(r.get(k) or 0)
    out["sent_count"] = int(r.get("sent_count") or 0)
    return out


def _to_db(vals):
    from ecentric_workspace.ai_tools.features.ai_live.repositories.health_repository import local_dt
    out = dict(vals)
    for ts, dt in _DT.items():
        if ts in vals:
            out[dt] = local_dt(vals[ts]) if vals[ts] else None
    for k in ("text", "title", "ack_note", "resolve_text"):
        if k in out and out[k] is not None:
            out[k] = str(out[k])[:C.MAX_INC_NOTE if k == "ack_note" else 1000]
    return out


class IncidentRepository:
    def open_by_key(self, key):
        import frappe
        rows = frappe.get_all(C.INCIDENT, filters={"incident_key": key, "status": ["in", [C.IncStatus.OPEN, C.IncStatus.ACKED]]},
                              fields=FIELDS, order_by="opened_ts desc", limit_page_length=1)
        return _row(rows[0]) if rows else None

    def open_all(self, kind=None):
        import frappe
        f = {"status": ["in", [C.IncStatus.OPEN, C.IncStatus.ACKED]]}
        if kind:
            f["kind"] = kind
        return [_row(r) for r in frappe.get_all(C.INCIDENT, filters=f, fields=FIELDS, order_by="opened_ts asc",
                                                limit_page_length=1000)]

    def get(self, name):
        import frappe
        rows = frappe.get_all(C.INCIDENT, filters={"name": name}, fields=FIELDS, limit=1) if name else []
        return _row(rows[0]) if rows else None

    def insert(self, row):
        import frappe
        doc = frappe.get_doc(dict(_to_db(row), doctype=C.INCIDENT))
        doc.insert(ignore_permissions=True)
        return doc.name

    def update(self, name, vals):
        import frappe
        frappe.db.set_value(C.INCIDENT, name, _to_db(vals), update_modified=False)

    def by_status(self, status, since_ts, limit=C.INC_LIST_MAX):
        import frappe
        f = {"status": status}
        if status == C.IncStatus.DONE:
            f["resolved_ts"] = [">=", since_ts]
        return [_row(r) for r in frappe.get_all(C.INCIDENT, filters=f, fields=FIELDS, order_by="opened_ts desc",
                                                limit_page_length=limit)]

    def counts(self, since_ts):
        import frappe
        rows = frappe.db.sql("select status, count(*) n from `tabEC AI Live Incident` where status!=%s or resolved_ts>=%s "
                             "group by status", (C.IncStatus.DONE, since_ts), as_dict=True)
        return {r.status: int(r.n) for r in rows}

    def purge(self, before_ts):
        import frappe
        frappe.db.sql("delete from `tabEC AI Live Incident` where status=%s and resolved_ts < %s", (C.IncStatus.DONE, before_ts))

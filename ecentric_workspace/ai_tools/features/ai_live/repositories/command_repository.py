# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Command: hang lenh tu trang ERP cho app tren may phat (tam dung AI, bo clip, phat FAQ)."""
import json

from ecentric_workspace.ai_tools.features.ai_live import constants as C

FIELDS = ["name", "live", "machine", "action", "args_json", "status", "created_ts", "sent_ts", "done_ts", "result",
          "requested_by"]


def _row(r):
    try:
        args = json.loads(r.get("args_json") or "{}") or {}
    except ValueError:
        args = {}
    return {"id": r["name"], "live": r.get("live"), "machine": r.get("machine"), "action": r.get("action"),
            "args": args, "status": r.get("status"), "created_ts": float(r.get("created_ts") or 0),
            "sent_ts": float(r.get("sent_ts") or 0), "done_ts": float(r.get("done_ts") or 0),
            "result": r.get("result") or "", "requested_by": r.get("requested_by") or ""}


class CommandRepository:
    def insert(self, row):
        import frappe
        doc = frappe.get_doc({"doctype": C.COMMAND, "live": row["live"], "machine": row["machine"],
                              "action": row["action"], "args_json": json.dumps(row.get("args") or {}, ensure_ascii=False),
                              "status": C.CMD_QUEUED, "created_ts": row["created_ts"],
                              "requested_by": row.get("requested_by") or ""})
        doc.insert(ignore_permissions=True)
        return doc.name

    def pending(self, machine):
        import frappe
        rows = frappe.get_all(C.COMMAND, filters={"machine": machine, "status": C.CMD_QUEUED}, fields=FIELDS,
                              order_by="created_ts asc", limit_page_length=C.CMD_PULL_MAX * 3)
        return [_row(r) for r in rows]

    def get(self, name):
        import frappe
        rows = frappe.get_all(C.COMMAND, filters={"name": name}, fields=FIELDS, limit=1) if name else []
        return _row(rows[0]) if rows else None

    def set_status(self, name, status, ts_field=None, ts=None, result=None):
        import frappe
        vals = {"status": status}
        if ts_field:
            vals[ts_field] = ts
        if result is not None:
            vals["result"] = str(result)[:C.MAX_CMD_RESULT]
        frappe.db.set_value(C.COMMAND, name, vals, update_modified=False)

    def recent(self, live, since_ts, limit=20):
        import frappe
        rows = frappe.get_all(C.COMMAND, filters={"live": live, "created_ts": [">=", since_ts]}, fields=FIELDS,
                              order_by="created_ts desc", limit_page_length=limit)
        return [_row(r) for r in rows]

    def purge(self, before_ts):
        import frappe
        frappe.db.delete(C.COMMAND, {"created_ts": ["<", before_ts]})

# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Health: 1 dong = tin hieu moi nhat cua 1 live tren 1 may (ghi de moi lan)."""
import datetime
import json

from ecentric_workspace.ai_tools.features.ai_live import constants as C

_JSON = ("metrics", "alerts", "schedule")


def _row(d):
    out = {"key": d.get("name"), "machine": d.get("machine"), "live": d.get("live"), "brand": d.get("brand") or "",
           "state": d.get("state") or "", "app_version": d.get("app_version") or "",
           "last_seen_ts": float(d.get("last_seen_ts") or 0), "obs_thumb_ts": float(d.get("obs_thumb_ts") or 0),
           "phone_thumb_ts": float(d.get("phone_thumb_ts") or 0), "offline_alerted": int(d.get("offline_alerted") or 0)}
    for k in _JSON:
        try:
            out[k] = json.loads(d.get(k + "_json") or "null") or ([] if k != "metrics" else {})
        except ValueError:
            out[k] = [] if k != "metrics" else {}
    return out


_FIELDS = ["name", "machine", "live", "brand", "state", "app_version", "last_seen_ts", "obs_thumb_ts",
           "phone_thumb_ts", "offline_alerted", "metrics_json", "alerts_json", "schedule_json"]


def local_dt(ts):
    """epoch giay -> datetime gio he thong (khong tz) de luu truong Datetime."""
    import frappe
    utc = datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc).replace(tzinfo=None)
    return frappe.utils.convert_utc_to_system_timezone(utc).replace(tzinfo=None)


class HealthRepository:
    def get(self, key):
        import frappe
        rows = frappe.get_all(C.HEALTH, filters={"name": key}, fields=_FIELDS, limit=1)
        return _row(rows[0]) if rows else None

    def all(self):
        import frappe
        return [_row(r) for r in frappe.get_all(C.HEALTH, fields=_FIELDS, order_by="brand asc, machine asc, live asc",
                                                limit_page_length=500)]

    def upsert(self, key, row):
        """row: machine, live, brand, state, app_version, last_seen_ts, metrics, alerts, schedule (+ *_thumb_ts)."""
        import frappe
        vals = {k: v for k, v in row.items() if k not in _JSON}
        for k in _JSON:
            if k in row:
                vals[k + "_json"] = json.dumps(row[k], ensure_ascii=False)
        if "last_seen_ts" in row:
            vals["last_seen"] = local_dt(row["last_seen_ts"])
        if frappe.db.exists(C.HEALTH, key):
            frappe.db.set_value(C.HEALTH, key, vals, update_modified=False)
        else:
            frappe.get_doc(dict(vals, doctype=C.HEALTH, health_key=key)).insert(ignore_permissions=True)

    def set_flag(self, key, offline_alerted):
        import frappe
        frappe.db.set_value(C.HEALTH, key, "offline_alerted", 1 if offline_alerted else 0, update_modified=False)

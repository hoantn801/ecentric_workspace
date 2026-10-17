# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Health Sample: so lieu gon moi phut cua 1 live, giu 24 gio (ve bieu do 1 gio)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C

SAMPLE_FIELDS = ("fps", "drop_pct", "gpu", "kbps")


class HealthSampleRepository:
    def last_ts(self, key):
        import frappe
        r = frappe.db.sql("select max(ts) from `tabEC AI Live Health Sample` where health_key=%s", (key,))
        return float(r[0][0] or 0) if r else 0.0

    def insert(self, key, ts, level, metrics):
        import frappe
        doc = {"doctype": C.HEALTH_SAMPLE, "health_key": key, "ts": ts, "level": level}
        for f in SAMPLE_FIELDS:
            if metrics.get(f) is not None:
                doc[f] = metrics[f]
        frappe.get_doc(doc).insert(ignore_permissions=True)

    def since(self, key, ts):
        import frappe
        rows = frappe.db.sql("select ts, fps, drop_pct, gpu, kbps, level from `tabEC AI Live Health Sample` "
                             "where health_key=%s and ts>=%s order by ts asc limit 200", (key, ts), as_dict=True)
        return [{"ts": float(r.ts), "fps": r.fps, "drop_pct": r.drop_pct, "gpu": r.gpu, "kbps": r.kbps,
                 "level": r.level} for r in rows]

    def purge(self, before_ts):
        import frappe
        frappe.db.sql("delete from `tabEC AI Live Health Sample` where ts < %s", (before_ts,))

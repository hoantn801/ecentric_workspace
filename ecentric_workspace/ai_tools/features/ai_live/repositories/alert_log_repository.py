# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Alert: lich su tin bao dong da gui (chong lap 10 phut + xem lai tren man Giam sat)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C


class AlertLogRepository:
    def last_sent(self, alert_key):
        import frappe
        r = frappe.db.sql("select sent_ts, level from `tabEC AI Live Alert` where alert_key=%s "
                          "order by sent_ts desc limit 1", (alert_key,), as_dict=True)
        return {"ts": float(r[0].sent_ts or 0), "level": r[0].level} if r else None

    def insert(self, row):
        """row: alert_key, health_key, machine, live, brand, level, code, text, sent_ts, teams_result, zalo_result."""
        import frappe

        from ecentric_workspace.ai_tools.features.ai_live.repositories.health_repository import local_dt
        sent_at = local_dt(row["sent_ts"])
        frappe.get_doc(dict(row, doctype=C.ALERT_LOG, sent_at=sent_at)).insert(ignore_permissions=True)

    def for_key(self, health_key, since_ts, limit=50):
        import frappe
        rows = frappe.db.sql("select sent_ts, level, code, text, teams_result, zalo_result from `tabEC AI Live Alert` "
                             "where health_key=%s and sent_ts>=%s order by sent_ts desc limit %s",
                             (health_key, since_ts, int(limit)), as_dict=True)
        return [{"ts": float(r.sent_ts), "level": r.level, "code": r.code, "text": r.text,
                 "teams": r.teams_result or "", "zalo": r.zalo_result or ""} for r in rows]

    def latest_by_key(self, since_ts):
        """{health_key: {ts, level, text}} - tin moi nhat cua tung live (hien tren o)."""
        import frappe
        rows = frappe.db.sql("select a.health_key, a.sent_ts, a.level, a.text from `tabEC AI Live Alert` a join "
                             "(select health_key, max(sent_ts) m from `tabEC AI Live Alert` where sent_ts>=%s "
                             "group by health_key) b on a.health_key=b.health_key and a.sent_ts=b.m", (since_ts,), as_dict=True)
        return {r.health_key: {"ts": float(r.sent_ts), "level": r.level, "text": r.text} for r in rows}

    def purge(self, before_ts):
        import frappe
        frappe.db.sql("delete from `tabEC AI Live Alert` where sent_ts < %s", (before_ts,))

# Copyright (c) 2026, eCentric and contributors
"""fix10g: so phien ban lich (EC AI Live Schedule Settings, Single) + nhat ky phat hanh (EC AI Live Schedule Version)."""
import json

from ecentric_workspace.ai_tools.features.ai_live import constants as C

_FIELDS = ["version", "source", "published_by", "published_ts", "note", "sessions", "machines", "changes_json"]


class ScheduleRepository:
    def settings(self):
        import frappe
        doc = frappe.get_single(C.SCHEDULE_SETTINGS)
        return {"version": int(doc.get("current_version") or 0), "lock_min": int(doc.get("lock_minutes") or C.LOCK_MIN),
                "refresh_on_publish": int(doc.get("refresh_on_publish") or 0),
                "last_published_by": doc.get("last_published_by") or "", "last_published_at": str(doc.get("last_published_at") or "")}

    def next_version(self, user, ts):
        """Tang so phien ban (khoa dong de 2 nguoi phat hanh cung luc khong trung so)."""
        import frappe

        from ecentric_workspace.ai_tools.features.ai_live.repositories.health_repository import local_dt
        r = frappe.db.sql("select value from `tabSingles` where doctype=%s and field='current_version' for update",
                          (C.SCHEDULE_SETTINGS,))
        v = int((r[0][0] if r else 0) or 0) + 1
        frappe.db.set_single_value(C.SCHEDULE_SETTINGS, {"current_version": v, "last_published_by": user,
                                                         "last_published_at": local_dt(ts)})
        return v

    def insert_version(self, row):
        """row: version, source, published_by, published_ts, note, sessions[], machines[], changes[]."""
        import frappe

        from ecentric_workspace.ai_tools.features.ai_live.repositories.health_repository import local_dt
        frappe.get_doc({"doctype": C.SCHEDULE_VERSION, "version": row["version"], "source": row["source"],
                        "published_by": row["published_by"], "published_ts": row["published_ts"],
                        "published_at": local_dt(row["published_ts"]), "note": row.get("note") or "",
                        "sessions": "\n".join(row["sessions"]), "machines": "\n".join(row["machines"]),
                        "changes_json": json.dumps(row["changes"], ensure_ascii=False)}).insert(ignore_permissions=True)

    def versions(self, limit=C.MAX_VERSION_LOG):
        import frappe
        rows = frappe.get_all(C.SCHEDULE_VERSION, fields=_FIELDS, order_by="published_ts desc", limit_page_length=int(limit))
        out = []
        for r in rows:
            try:
                ch = json.loads(r.get("changes_json") or "[]") or []
            except ValueError:
                ch = []
            out.append({"version": int(r.get("version") or 0), "source": r.get("source") or "", "by": r.get("published_by") or "",
                        "ts": float(r.get("published_ts") or 0), "note": r.get("note") or "", "changes": ch,
                        "machines": [x for x in str(r.get("machines") or "").splitlines() if x]})
        return out

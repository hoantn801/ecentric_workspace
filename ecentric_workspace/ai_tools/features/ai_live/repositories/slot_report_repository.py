# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Slot Report (fix10h): ke hoach vs thuc te tung khung, khoa (may, live, planned_start) - ghi de."""
import json

from ecentric_workspace.ai_tools.features.ai_live import constants as C

_TS = ("planned_start_ts", "planned_end_ts", "actual_start_ts", "actual_end_ts", "updated_ts", "received_ts")
FIELDS = ["name", "machine", "live", "brand", "date", "status", "start_status", "start_delay_sec", "downtime_sec",
          "ai_failover_count", "alerts_critical", "note", "final", "session_id", "off_plan", "interruptions_json"] + list(_TS)
_DT = {"planned_start_ts": "planned_start", "actual_start_ts": "actual_start", "actual_end_ts": "actual_end"}


def _row(r):
    out = {k: r.get(k) for k in FIELDS if k != "interruptions_json"}
    for k in _TS:
        out[k] = float(r.get(k) or 0)
    out["date"] = str(r.get("date") or "")
    sd = r.get("start_delay_sec")
    out["start_delay_sec"] = None if sd is None else int(sd)
    for k in ("downtime_sec", "ai_failover_count", "alerts_critical", "final", "off_plan"):
        out[k] = int(r.get(k) or 0)
    try:
        out["interruptions"] = json.loads(r.get("interruptions_json") or "[]") or []
    except ValueError:
        out["interruptions"] = []
    return out


def SR_older(row, cur):
    """Ban gui toi cu hon ban dang luu (theo updated_at cua app), hoac ban dang luu da chot ma ban moi chua chot."""
    if not cur:
        return False
    if int(cur.get("final") or 0) and not int(row.get("final") or 0):
        return True
    return float(row.get("updated_ts") or 0) < float(cur.get("updated_ts") or 0)


class SlotReportRepository:
    def upsert(self, key, row):
        import frappe

        from ecentric_workspace.ai_tools.features.ai_live.repositories.health_repository import local_dt
        vals = {k: v for k, v in row.items() if k != "interruptions"}
        vals["interruptions_json"] = json.dumps(row.get("interruptions") or [], ensure_ascii=False)
        for ts, dt in _DT.items():
            if ts in row:
                vals[dt] = local_dt(row[ts]) if row[ts] else None
        cur = frappe.db.get_value(C.SLOT_REPORT, key, ["updated_ts", "final"], as_dict=True)
        if not cur:
            try:
                frappe.get_doc(dict(vals, doctype=C.SLOT_REPORT, report_key=key)).insert(ignore_permissions=True)
                return
            except frappe.DuplicateEntryError:      # 2 lo cung khung gui dong thoi -> chuyen sang ghi de
                cur = frappe.db.get_value(C.SLOT_REPORT, key, ["updated_ts", "final"], as_dict=True) or {}
        if SR_older(row, cur):
            return                                  # lo cu gui lai muon: khong de len ban moi hon / ban da chot
        # o Int cua Frappe NOT NULL: bo truong None (vd start_delay_sec khi lo) thay vi ghi NULL
        frappe.db.set_value(C.SLOT_REPORT, key, {k: v for k, v in vals.items() if v is not None}, update_modified=False)

    def for_dates(self, dates):
        import frappe
        return [_row(r) for r in frappe.get_all(C.SLOT_REPORT, filters={"date": ["in", list(dates)]}, fields=FIELDS,
                                                order_by="planned_start_ts asc", limit_page_length=2000)]

    def purge(self, before_ts):
        import frappe
        frappe.db.sql("delete from `tabEC AI Live Slot Report` where planned_start_ts < %s", (before_ts,))

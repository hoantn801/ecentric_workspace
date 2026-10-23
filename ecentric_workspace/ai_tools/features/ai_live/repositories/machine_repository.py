# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Machine + User may phat (token API Frappe = api_key:api_secret).
fix10f: nhip tim ca may (hb_*) + moc bao dong may im lang (watch_*) ghi thang bang set_value, khong doi modified."""
import json

from ecentric_workspace.ai_tools.features.ai_live import constants as C

_TS = ("hb_last_seen_ts", "hb_boot_ts", "hb_started_ts", "watch_lost_ts", "watch_back_ts", "watch_sent_ts",
       "watch_lost_boot_ts", "watch_lost_started_ts", "cfg_fetched_ts", "hb_clock_skew_s")
_HB_FIELDS = list(_TS) + ["hb_state", "hb_version", "hb_on_air", "hb_lives_json", "hb_resume_crash", "watch_brands",
                          "cfg_version", "hb_alerts", "hb_resume"]
#: truong epoch -> truong Datetime de nguoi xem tren Desk
_DT = {"hb_last_seen_ts": "hb_last_seen", "hb_boot_ts": "hb_boot_at", "hb_started_ts": "hb_app_started_at",
       "cfg_fetched_ts": "cfg_fetched_at"}


def _hb(d):
    out = {k: float(d.get(k) or 0) for k in _TS}
    out.update({"hb_state": d.get("hb_state") or "", "hb_version": d.get("hb_version") or "",
                "hb_on_air": int(d.get("hb_on_air") or 0), "hb_resume_crash": int(d.get("hb_resume_crash") or 0),
                "cfg_version": int(d.get("cfg_version") or 0),
                "watch_brands": [b for b in str(d.get("watch_brands") or "").splitlines() if b],
                "hb_alerts": [a for a in str(d.get("hb_alerts") or "").splitlines() if a], "hb_resume": d.get("hb_resume") or ""})
    try:
        out["hb_lives"] = json.loads(d.get("hb_lives_json") or "[]") or []
    except ValueError:
        out["hb_lives"] = []
    return out


def _to_db(vals):
    from ecentric_workspace.ai_tools.features.ai_live.repositories.health_repository import local_dt
    out = {k: v for k, v in vals.items() if k not in ("hb_lives", "hb_alerts", "watch_brands")}
    for ts, dt in _DT.items():
        if ts in vals:
            out[dt] = local_dt(vals[ts]) if vals[ts] else None
    if "hb_lives" in vals:
        out["hb_lives_json"] = json.dumps(vals["hb_lives"], ensure_ascii=False)
        out["hb_lives"] = "\n".join("%s – %s" % (x["brand"], x["live"]) if x.get("brand") else x["live"]
                                    for x in vals["hb_lives"])
    if "hb_alerts" in vals:
        out["hb_alerts"] = "\n".join(vals["hb_alerts"])
        out["hb_alert_count"] = len(vals["hb_alerts"])
    if "watch_brands" in vals:
        out["watch_brands"] = "\n".join(vals["watch_brands"])
    return out


class MachineRepository:
    def by_user(self, user):
        import frappe
        name = frappe.db.get_value(C.MACHINE, {"user": user}, "name")
        return self.get(name) if name else None

    def get(self, code):
        import frappe
        if not code or not frappe.db.exists(C.MACHINE, code):
            return None
        doc = frappe.get_doc(C.MACHINE, code)
        return dict(_hb(doc.as_dict()), machine_code=doc.name, label=doc.label, enabled=int(doc.enabled or 0),
                    user=doc.user, brands=doc.brands or "", max_lives=int(doc.get("max_lives") or 0) or C.DEFAULT_MAX_LIVES)

    def heartbeats(self):
        """May dang dung da tung gui nhip tim (fix10f: quet may im lang)."""
        import frappe
        rows = frappe.get_all(C.MACHINE, filters={"enabled": 1, "hb_last_seen_ts": [">", 0]},
                              fields=["name", "label", "brands"] + _HB_FIELDS, order_by="name asc", limit_page_length=200)
        return [dict(_hb(r), machine_code=r["name"], label=r.get("label") or "", brands=r.get("brands") or "")
                for r in rows]

    def save_heartbeat(self, code, vals):
        import frappe
        frappe.db.set_value(C.MACHINE, code, _to_db(vals), update_modified=False)

    def set_watch(self, code, vals):
        self.save_heartbeat(code, vals)

    def record_fetch(self, code, ts, version):
        """fix10g: may vua tai get_config (= da nhan lich ban `version`)."""
        self.save_heartbeat(code, {"cfg_fetched_ts": ts, "cfg_version": int(version or 0)})

    def sync_states(self):
        """fix10g: moi may (ca may tat) + trang thai nhan lich, de man Dong bo / Gantt hien."""
        import frappe
        rows = frappe.get_all(C.MACHINE, fields=["name", "label", "enabled", "max_lives", "brands"] + _HB_FIELDS,
                              order_by="name asc", limit_page_length=200)
        return [dict(_hb(r), machine_code=r["name"], label=r.get("label") or "", enabled=int(r.get("enabled") or 0),
                     max_lives=int(r.get("max_lives") or 0) or C.DEFAULT_MAX_LIVES, brands=r.get("brands") or "")
                for r in rows]

    def all(self):
        """Moi may phat (cho trang Phien live / Lich live): ma, ten, bat/tat, so live toi da, brand."""
        import frappe
        rows = frappe.get_all(C.MACHINE, fields=["name", "label", "enabled", "max_lives", "brands"],
                              order_by="name asc", limit_page_length=200)
        return [{"machine_code": r["name"], "label": r.get("label") or "", "enabled": int(r.get("enabled") or 0),
                 "max_lives": int(r.get("max_lives") or 0) or C.DEFAULT_MAX_LIVES, "brands": r.get("brands") or ""}
                for r in rows]

    def upsert(self, code, label, brands):
        import frappe
        if frappe.db.exists(C.MACHINE, code):
            doc = frappe.get_doc(C.MACHINE, code)
        else:
            doc = frappe.get_doc({"doctype": C.MACHINE, "machine_code": code, "enabled": 1})
        if label is not None:
            doc.label = label
        if brands is not None:
            doc.brands = brands
        doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)
        return doc.name

    def ensure_user(self, code):
        """User Website (khong vao Desk) cho may phat; tra ten user."""
        import frappe
        email = C.MACHINE_EMAIL % code.lower()
        if not frappe.db.exists("User", email):
            frappe.get_doc({"doctype": "User", "email": email, "first_name": "AI Live %s" % code,
                            "user_type": "Website User", "send_welcome_email": 0, "enabled": 1}).insert(ignore_permissions=True)
        frappe.db.set_value(C.MACHINE, code, "user", email)
        return email

    def rotate_keys(self, user):
        """Tao api_key/api_secret moi cho user may phat. Tra 'key:secret' (chi hien 1 lan)."""
        import frappe
        doc = frappe.get_doc("User", user)
        key, secret = frappe.generate_hash(length=15), frappe.generate_hash(length=15)
        doc.api_key = key
        doc.api_secret = secret
        doc.save(ignore_permissions=True)
        return "%s:%s" % (key, secret)

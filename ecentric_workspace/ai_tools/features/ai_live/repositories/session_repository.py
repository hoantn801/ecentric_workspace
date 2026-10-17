# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Session (+ bang con EC AI Live Session Slot). Tra dict; khung gio dang
{days:[1..7], date|None, start, end} (giong domain/session_rules.norm_slots)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C

FIELDS = ["name", "title", "brand", "platform", "shop_name", "tiktok_username", "machine", "obs_port", "kit", "mode",
          "auto_obs_start", "enabled", "watch_url", "phone_serial", "modified"]


def _days(v):
    out = []
    for x in str(v or "").replace(";", ",").split(","):
        x = x.strip()
        if "-" in x:
            a, _, b = x.partition("-")
            if a.strip().isdigit() and b.strip().isdigit():
                out.extend(range(int(a), int(b) + 1))
        elif x.isdigit():
            out.append(int(x))
    return sorted({d for d in out if 1 <= d <= 7})


def _slot(r):
    d = str(r.get("on_date") or "")[:10] or None
    return {"days": [] if d else (_days(r.get("days")) or list(range(1, 8))), "date": d,
            "start": r.get("slot_start") or "", "end": r.get("slot_end") or ""}


def _row(r, slots):
    return {"id": r["name"], "title": r.get("title") or r["name"], "brand": r.get("brand") or "",
            "platform": r.get("platform") or "", "shop_name": r.get("shop_name") or "",
            "tiktok_username": r.get("tiktok_username") or "", "machine": r.get("machine") or "",
            "obs_port": int(r.get("obs_port") or 0), "kit": r.get("kit") or "", "mode": r.get("mode") or "",
            "auto_obs_start": int(r.get("auto_obs_start") or 0), "enabled": int(r.get("enabled") or 0),
            "watch_url": r.get("watch_url") or "", "phone_serial": r.get("phone_serial") or "",
            "updated_at": str(r.get("modified") or ""), "slots": slots}


class SessionRepository:
    def _slots_for(self, names):
        import frappe
        if not names:
            return {}
        rows = frappe.get_all(C.SESSION_SLOT, filters={"parent": ["in", list(names)], "parenttype": C.SESSION},
                              fields=["parent", "idx", "days", "on_date", "slot_start", "slot_end"],
                              order_by="parent asc, idx asc", limit_page_length=C.MAX_SESSIONS * C.MAX_SESSION_SLOTS)
        out = {}
        for r in rows:
            out.setdefault(r["parent"], []).append(_slot(r))
        return out

    def list(self, filters=None):
        import frappe
        rows = frappe.get_all(C.SESSION, filters=filters or {}, fields=FIELDS, order_by="brand asc, title asc",
                              limit_page_length=C.MAX_SESSIONS)
        slots = self._slots_for([r["name"] for r in rows])
        return [_row(r, slots.get(r["name"], [])) for r in rows]

    def get(self, name):
        rows = self.list({"name": name}) if name else []
        return rows[0] if rows else None

    def by_machine(self, machine):
        return self.list({"machine": machine}) if machine else []

    def save_slots(self, name, slots):
        """Thay toan bo khung gio cua phien (chay validate cua DocType)."""
        import frappe
        doc = frappe.get_doc(C.SESSION, name)
        doc.set("slots", [{"days": ",".join(str(d) for d in s["days"]) if not s["date"] else "",
                           "on_date": s["date"], "slot_start": s["start"], "slot_end": s["end"]} for s in slots])
        doc.save(ignore_permissions=True)
        return doc.name

    def set_enabled(self, names, enabled):
        import frappe
        done = []
        for n in names:
            if frappe.db.exists(C.SESSION, n):
                doc = frappe.get_doc(C.SESSION, n)
                doc.enabled = 1 if enabled else 0
                doc.save(ignore_permissions=True)
                done.append(n)
        return done

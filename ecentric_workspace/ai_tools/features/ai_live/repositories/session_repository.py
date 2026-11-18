# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Session (+ bang con EC AI Live Session Slot). Tra dict; khung gio dang
{days:[1..7], date|None, start, end} (giong domain/session_rules.norm_slots)."""
import json

from ecentric_workspace.ai_tools.features.ai_live import constants as C

FIELDS = ["name", "live_id", "title", "brand", "platform", "shop_name", "tiktok_username", "machine", "obs_port", "kit", "mode",
          "auto_obs_start", "enabled", "watch_url", "phone_serial", "modified",
          # fix10g: ban nhap / phat hanh / giu gio cu
          "draft_json", "draft_base_version", "draft_by", "draft_at", "published_version", "published_ts", "prev_json",
          "held_until_ts", "held_why", "published_source",
          "lc_open_before_min"]                 # 18/11: mo tab truoc gio live (phut), trong = theo app


def _json(v):
    try:
        return json.loads(v) if v else None
    except ValueError:
        return None


def _slot_rows(slots):
    from ecentric_workspace.ai_tools.features.ai_live.domain.session_rules import slot_on
    return [{"days": ",".join(str(d) for d in s["days"]) if not s["date"] else "", "on_date": s["date"],
             "slot_start": s["start"], "slot_end": s["end"], "enabled": 1 if slot_on(s) else 0} for s in slots]


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
    en = r.get("enabled")
    return {"days": [] if d else (_days(r.get("days")) or list(range(1, 8))), "date": d,
            "start": r.get("slot_start") or "", "end": r.get("slot_end") or "",
            "enabled": True if en is None else bool(int(en))}     # 18/11: dong cu chua co cot = dang bat


def _row(r, slots):
    # 18/11 (tao phien tren /ai-live): phien = (may, ma live). "id" = ten document ({may}-{ma live}) - dung trong ERP;
    # "live" = ma live tren app (L1, L2...) - dung khi noi chuyen voi app / ghep bao cao (luon kem may).
    return {"id": r["name"], "live": r.get("live_id") or r["name"], "title": r.get("title") or r["name"],
            "brand": r.get("brand") or "",
            "platform": r.get("platform") or "", "shop_name": r.get("shop_name") or "",
            "tiktok_username": r.get("tiktok_username") or "", "machine": r.get("machine") or "",
            "obs_port": int(r.get("obs_port") or 0), "kit": r.get("kit") or "", "mode": r.get("mode") or "",
            "lc_open_before_min": int(r.get("lc_open_before_min") or 0) or None,
            "auto_obs_start": int(r.get("auto_obs_start") or 0), "enabled": int(r.get("enabled") or 0),
            "watch_url": r.get("watch_url") or "", "phone_serial": r.get("phone_serial") or "",
            "updated_at": str(r.get("modified") or ""), "slots": slots,
            "draft": _json(r.get("draft_json")), "draft_base_version": int(r.get("draft_base_version") or 0),
            "draft_by": r.get("draft_by") or "", "draft_at": str(r.get("draft_at") or ""),
            "published_version": int(r.get("published_version") or 0), "published_ts": float(r.get("published_ts") or 0),
            "prev": _json(r.get("prev_json")), "held_until_ts": float(r.get("held_until_ts") or 0),
            "held_why": r.get("held_why") or "", "published_source": r.get("published_source") or ""}


class SessionRepository:
    def _slots_for(self, names):
        import frappe
        if not names:
            return {}
        rows = frappe.get_all(C.SESSION_SLOT, filters={"parent": ["in", list(names)], "parenttype": C.SESSION},
                              fields=["parent", "idx", "days", "on_date", "slot_start", "slot_end", "enabled"],
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

    def find(self, machine, live):
        """18/11: phien cua 1 ma live tren 1 may (ma live chi duy nhat trong 1 may)."""
        rows = self.list({"machine": machine, "live_id": live}) if machine and live else []
        return rows[0] if rows else None

    def create(self, vals, slots, draft, user, ts):
        """18/11: tao phien tu ngan /ai-live - CHUA phat hanh: bang khung trong, ban nhap = toan bo (khung + truong);
        app chi nhan sau khi Phat hanh (published_version 0 + co nhap -> get_config bo qua)."""
        import frappe

        from ecentric_workspace.ai_tools.features.ai_live.repositories.health_repository import local_dt
        doc = frappe.new_doc(C.SESSION)
        doc.update(vals)
        doc.update({"draft_json": json.dumps(draft, ensure_ascii=False), "draft_base_version": 0, "draft_by": user,
                    "draft_at": local_dt(ts), "published_version": 0})
        doc.flags.ec_create = True
        doc.insert(ignore_permissions=True)
        return doc.name

    def save_slots(self, name, slots):
        """Thay toan bo khung gio cua phien (chay validate cua DocType)."""
        import frappe
        doc = frappe.get_doc(C.SESSION, name)
        doc.set("slots", _slot_rows(slots))
        doc.save(ignore_permissions=True)
        return doc.name

    def save_draft(self, name, draft, base_version, user, ts):
        """fix10g: ghi / xoa ban nhap (draft=None) - khong dung toi lich dang phat hanh, khong doi modified."""
        import frappe

        from ecentric_workspace.ai_tools.features.ai_live.repositories.health_repository import local_dt
        frappe.db.set_value(C.SESSION, name, {"draft_json": json.dumps(draft, ensure_ascii=False) if draft else "",
                                              "draft_base_version": int(base_version or 0) if draft else 0,
                                              "draft_by": user if draft else "", "draft_at": local_dt(ts) if draft else None},
                            update_modified=False)

    def mirror_unpublished(self, name, vals):
        """18/11: phien chua phat hanh lan nao - chep ten / brand / san... trong nhap len ban ghi de danh sach, Dong bo,
        chi tiet hien dung (app chua nhan phien nay nen khong lech gi). Gia tri da kiem o session_form_rules."""
        import frappe
        frappe.db.set_value(C.SESSION, name, {k: (v if v not in ("",) else None) for k, v in vals.items()},
                            update_modified=False)

    def publish(self, name, view, meta):
        """fix10g: ghi ban phat hanh (khung, may, kenh, mo tab truoc) + moc phien ban / ban cu / giu gio; xoa ban nhap.
        Suc chua may da kiem tren ca bo truoc khi goi -> co flags.ec_publish de validate khong kiem lai tung phien."""
        import frappe
        doc = frappe.get_doc(C.SESSION, name)
        doc.flags.ec_publish = True
        doc.set("slots", _slot_rows(view["slots"]))
        doc.machine = view["machine"] or None
        doc.obs_port = int(view["obs_port"] or 0) or None
        doc.lc_open_before_min = int(view.get("lc_open_before_min") or 0) or None
        for k in C.SESSION_DRAFT_FIELDS:        # 18/11: cac truong khac cua phien cung di qua Nhap -> Phat hanh
            if k in view:
                doc.set(k, view[k] if view[k] not in ("",) else None)
        doc.update({"published_version": meta["version"], "published_ts": meta["ts"], "published_source": meta["source"],
                    "prev_json": json.dumps(meta["prev"], ensure_ascii=False) if meta.get("prev") else "",
                    "held_until_ts": meta.get("held_until") or 0, "held_why": meta.get("held_why") or ""})
        if not meta.get("keep_draft"):          # app sua lich: giu ban nhap cua nguoi tren ERP (thanh "lech")
            doc.update({"draft_json": "", "draft_base_version": 0, "draft_by": "", "draft_at": None})
        doc.save(ignore_permissions=True)
        return doc.name

    def set_hold(self, name, until, why):
        import frappe
        frappe.db.set_value(C.SESSION, name, {"held_until_ts": until, "held_why": why}, update_modified=False)

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

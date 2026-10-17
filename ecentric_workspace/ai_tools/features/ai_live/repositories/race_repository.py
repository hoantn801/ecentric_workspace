# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Race (+ bang con EC AI Live Race Winner). 1 ban ghi = 1 cuoc dua vit (ten = ma cuoc dua).
Anh xep hang luu thanh File rieng tu gan vao ban ghi (truong ranking_png)."""
import datetime
import json

from ecentric_workspace.ai_tools.features.ai_live import constants as C

FIELDS = ["name", "live", "brand", "machine", "app_session", "keyword", "status_raw", "outcome", "race_date",
          "reg_started_ts", "race_started_ts", "finished_ts", "sort_ts", "entrants", "registered", "excluded_count",
          "excluded_json", "tiers_json", "seed", "audit_id", "algo", "triggered_by", "auto", "ranking_png", "png_sha256",
          "winners_n", "awarded_n", "unreachable_n", "modified"]
W_FIELDS = ["parent", "race_rank", "tier", "prize", "winner_name", "prize_status", "note", "app_status", "app_note"]


def _dt(ts):
    import frappe
    if not ts:
        return None
    utc = datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc).replace(tzinfo=None)
    return frappe.utils.convert_utc_to_system_timezone(utc).replace(tzinfo=None)


def _json(v, default):
    try:
        return json.loads(v) if v else default
    except ValueError:
        return default


def _w(r):
    return {"rank": int(r.get("race_rank") or 0), "tier": r.get("tier") or "", "prize": r.get("prize") or "",
            "name": r.get("winner_name") or "", "status": r.get("prize_status") or C.PRIZE_STATUS[C.PRIZE_DEFAULT],
            "note": r.get("note") or "", "app_status": r.get("app_status") or "", "app_note": r.get("app_note") or ""}


def _row(r, winners):
    out = {"id": r["name"], "live": r.get("live") or "", "brand": r.get("brand") or "", "machine": r.get("machine") or "",
           "app_session": r.get("app_session") or "", "keyword": r.get("keyword") or "", "status_raw": r.get("status_raw") or "",
           "outcome": r.get("outcome") or "", "race_date": str(r.get("race_date") or ""),
           "entrants": int(r.get("entrants") or 0), "registered": int(r.get("registered") or 0),
           "excluded_count": int(r.get("excluded_count") or 0), "excluded_reasons": _json(r.get("excluded_json"), []),
           "tiers": _json(r.get("tiers_json"), []), "seed": r.get("seed") or "", "audit_id": r.get("audit_id") or "",
           "algo": r.get("algo") or "", "by": r.get("triggered_by") or "", "auto": int(r.get("auto") or 0),
           "png_url": r.get("ranking_png") or "", "png_sha256": r.get("png_sha256") or "",
           "winners_n": int(r.get("winners_n") or 0), "awarded_n": int(r.get("awarded_n") or 0),
           "unreachable_n": int(r.get("unreachable_n") or 0), "updated_at": str(r.get("modified") or ""),
           "winners": winners}
    for k in ("reg_started_ts", "race_started_ts", "finished_ts", "sort_ts"):
        out[k] = float(r.get(k) or 0) or None
    return out


class RaceRepository:
    def _winners(self, names):
        import frappe
        if not names:
            return {}
        rows = frappe.get_all(C.RACE_WINNER, filters={"parent": ["in", list(names)], "parenttype": C.RACE}, fields=W_FIELDS,
                              order_by="parent asc, race_rank asc", limit_page_length=len(names) * C.MAX_RACE_WINNERS)
        out = {}
        for r in rows:
            out.setdefault(r["parent"], []).append(_w(r))
        return out

    def list(self, date_from, date_to, brand=None, live=None, outcome=None, limit=C.RACE_LIST_MAX):
        import frappe
        filters = [["race_date", ">=", date_from], ["race_date", "<=", date_to]]
        for f, v in (("brand", brand), ("live", live), ("outcome", outcome)):
            if v:
                filters.append([f, "=", v])
        rows = frappe.get_all(C.RACE, filters=filters, fields=FIELDS, order_by="sort_ts desc", limit_page_length=limit)
        ws = self._winners([r["name"] for r in rows])
        return [_row(r, ws.get(r["name"], [])) for r in rows]

    def get(self, rid):
        import frappe
        rows = frappe.get_all(C.RACE, filters={"name": rid}, fields=FIELDS, limit_page_length=1) if rid else []
        return _row(rows[0], self._winners([rows[0]["name"]]).get(rows[0]["name"], [])) if rows else None

    def upsert(self, race, winners, machine):
        """Ghi de ket qua + bang nguoi thang (trang thai trao giai da gop san o service)."""
        import frappe
        vals = {"live": race["live"], "brand": race["brand"], "machine": machine, "app_session": race["app_session"],
                "keyword": race["keyword"], "status_raw": race["status_raw"], "outcome": race["outcome"],
                "race_date": race["race_date"], "reg_started_ts": race["reg_started_ts"],
                "race_started_ts": race["race_started_ts"], "finished_ts": race["finished_ts"], "sort_ts": race["sort_ts"],
                "started_at": _dt(race["reg_started_ts"] or race["sort_ts"]), "entrants": race["entrants"],
                "registered": race["registered"], "excluded_count": race["excluded_count"],
                "excluded_json": json.dumps(race["excluded_reasons"], ensure_ascii=False),
                "tiers_json": json.dumps(race["tiers"], ensure_ascii=False), "seed": race["seed"],
                "audit_id": race["audit_id"], "algo": race["algo"], "triggered_by": race["by"], "auto": 1 if race["auto"] else 0}
        exists = frappe.db.exists(C.RACE, race["id"])
        doc = frappe.get_doc(C.RACE, race["id"]) if exists else frappe.new_doc(C.RACE)
        if not exists:
            doc.race_id = race["id"]
        doc.update(vals)
        doc.set("winners", [{"race_rank": w["rank"], "tier": w["tier"], "prize": w["prize"], "winner_name": w["name"],
                             "prize_status": w["status"], "note": w["note"], "app_status": w["app_status"],
                             "app_note": w["app_note"]} for w in winners])
        doc.save(ignore_permissions=True) if exists else doc.insert(ignore_permissions=True)
        return doc.name

    def save_png(self, name, data, sha):
        """Anh xep hang -> File rieng tu gan vao ban ghi; xoa anh cu cua truong nay."""
        import frappe
        old = frappe.get_all("File", filters={"attached_to_doctype": C.RACE, "attached_to_name": name,
                                              "attached_to_field": "ranking_png"}, pluck="name")
        f = frappe.get_doc({"doctype": "File", "file_name": "dua_vit_%s.png" % name, "attached_to_doctype": C.RACE,
                            "attached_to_name": name, "attached_to_field": "ranking_png", "is_private": 1, "content": data})
        f.save(ignore_permissions=True)
        for n in old:
            if n != f.name:
                frappe.delete_doc("File", n, ignore_permissions=True, force=True)
        frappe.db.set_value(C.RACE, name, {"ranking_png": f.file_url, "png_sha256": sha}, update_modified=False)
        return f.file_url

    def set_prize_status(self, items, label, note=None):
        """items: [(ma cuoc dua, hang)]. Luu qua doc.save de con lich su sua (track_changes). Tra so dong da doi."""
        import frappe
        by_race = {}
        for rid, rank in items:
            by_race.setdefault(rid, set()).add(int(rank))
        done = 0
        for rid, ranks in by_race.items():
            if not frappe.db.exists(C.RACE, rid):
                continue
            doc = frappe.get_doc(C.RACE, rid)
            hit = False
            for row in doc.winners:
                if int(row.race_rank or 0) in ranks:
                    row.prize_status = label
                    if note is not None:
                        row.note = note
                    hit = True
                    done += 1
            if hit:
                doc.save(ignore_permissions=True)
        return done

# Copyright (c) 2026, eCentric and contributors
"""Dung lai EC AI Usage Log cho giai doan TRUOC khi co log (Hoan 07/10: "historical co nguoi
dung roi ma sao chua co data").

Chi khoi phuc duoc nhung tinh nang co de lai dau vet co nguoi + thoi diem:
  * formfill        <- EC AI Formfill Log (request_user, outcome, model, latency_ms)
  * company_summary <- Company Weekly Summary (generated_by, auto_generated, model_used)
  * weekly_report   <- Weekly Team Update da co ai_status (AI tu cham khi nop - tinh la
                       luot tu dong, khong tinh la nguoi nop "dung AI"; xem AUTO_PURPOSES)
  * post_cover      <- EC Post Cover Job (requested_by, status, model)
eC Mate, hoi dap so lieu, AI Content livestream, viet bai... truoc day KHONG luu gi -> khong
dung lai duoc. Dong khoi phuc co `backfilled=1`, khong co token / credit (khong biet).

Chi lay ban ghi TRUOC dong log that dau tien (sau do da co log that, lay nua la dem doi).
Chay mot lan: da co dong backfilled thi thoi.
"""
import frappe

DOCTYPE = "EC AI Usage Log"
SYSTEM_USER = "Administrator"
FIELDS = ["name", "creation", "modified", "owner", "modified_by", "docstatus",
          "user", "department", "purpose", "model", "ok", "fell_back", "attempts",
          "latency_ms", "input_tokens", "output_tokens", "total_tokens", "credits",
          "cost_source", "images", "error", "backfilled"]


def _row(user, purpose, when, model="", ok=1, latency_ms=0, department="", error=""):
    return {"user": user or SYSTEM_USER, "department": department or "", "purpose": purpose,
            "model": model or "", "ok": 1 if ok else 0, "fell_back": 0,
            "attempts": 1, "latency_ms": int(latency_ms or 0), "input_tokens": 0,
            "output_tokens": 0, "total_tokens": 0, "credits": 0.0, "cost_source": "",
            "images": 0, "error": (error or "")[:240], "backfilled": 1, "creation": when}


def from_formfill(r):
    out = r.get("outcome") or ""
    if out.startswith("refused"):          # bi chan truoc khi goi AI - khong phai mot luot AI
        return None
    return _row(r.get("request_user"), "formfill", r.get("creation"), r.get("model"),
                ok=out == "ok", latency_ms=r.get("latency_ms"),
                error="" if out == "ok" else out)


def from_company_summary(r):
    user = SYSTEM_USER if r.get("auto_generated") else (r.get("generated_by") or r.get("owner"))
    return _row(user, "company_summary", r.get("generated_at") or r.get("creation"),
                r.get("model_used"))


def from_weekly(r):
    return _row(r.get("owner"), "weekly_report", r.get("creation"),
                department=r.get("department"))


def from_post_cover(r):
    st = r.get("status") or ""
    return _row(r.get("requested_by") or r.get("owner"), "post_cover", r.get("creation"),
                r.get("model"), ok=st == "Done", error="" if st == "Done" else st)


def build(sources, dept_of, cutoff):
    """PURE. sources: {ten: (mapper, [ban ghi])} -> [dong], chi dong co creation < cutoff."""
    rows = []
    for mapper, records in sources.values():
        for rec in records or []:
            row = mapper(rec)
            if not row or not row["creation"]:
                continue
            if cutoff and str(row["creation"]) >= str(cutoff):
                continue
            if not row["department"] and row["user"] != SYSTEM_USER:
                row["department"] = dept_of.get(row["user"], "")
            rows.append(row)
    rows.sort(key=lambda x: str(x["creation"]))
    return rows


def _all(doctype, fields, filters=None):
    if not frappe.db.exists("DocType", doctype):
        return []
    meta = frappe.get_meta(doctype)
    keep = [f for f in fields if f in ("name", "owner", "creation") or meta.has_field(f)]
    return [dict(r) for r in frappe.get_all(doctype, filters=filters or {}, fields=keep,
                                            limit_page_length=0)]


def run():
    if frappe.db.exists(DOCTYPE, {"backfilled": 1}):
        return {"skipped": "already"}
    first = frappe.get_all(DOCTYPE, filters={"backfilled": 0}, fields=["creation"],
                           order_by="creation asc", limit_page_length=1)
    cutoff = str(first[0].creation) if first else frappe.utils.now()
    dept_of = {}
    for e in frappe.get_all("Employee", filters={"user_id": ["is", "set"]},
                            fields=["user_id", "department", "status"], limit_page_length=0):
        if e.status == "Active" or e.user_id not in dept_of:
            dept_of[e.user_id] = e.department or ""
    sources = {
        "formfill": (from_formfill, _all("EC AI Formfill Log",
                     ["creation", "request_user", "outcome", "model", "latency_ms"])),
        "company_summary": (from_company_summary, _all("Company Weekly Summary",
                            ["creation", "owner", "generated_by", "generated_at",
                             "auto_generated", "model_used"])),
        "weekly_report": (from_weekly, _all("Weekly Team Update",
                          ["creation", "owner", "department"], {"ai_status": ["is", "set"]})),
        "post_cover": (from_post_cover, _all("EC Post Cover Job",
                       ["creation", "owner", "requested_by", "status", "model"])),
    }
    rows = build(sources, dept_of, cutoff)
    values = []
    for r in rows:
        values.append(tuple([frappe.generate_hash(length=10), r["creation"], r["creation"],
                             SYSTEM_USER, SYSTEM_USER, 0] + [r[f] for f in FIELDS[6:]]))
    for i in range(0, len(values), 500):
        frappe.db.bulk_insert(DOCTYPE, FIELDS, values[i:i + 500], ignore_duplicates=True)
    counts = {}
    for r in rows:
        counts[r["purpose"]] = counts.get(r["purpose"], 0) + 1
    return {"inserted": len(rows), "cutoff": cutoff, "by_purpose": counts}

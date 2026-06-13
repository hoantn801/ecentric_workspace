"""Phase 3 backfill: promote SKU Catalog `note` JSON -> real fields (2026-06-13).

Idempotent, rerun-safe, non-destructive. For every SKU Catalog row that has a
catalogue `note` JSON payload, populate any EMPTY promoted field from the JSON.

Hard rules (locked):
  * NEVER modify `rsp_price` (order-derived priority).
  * NEVER overwrite a promoted field that is already populated (rerun = no-op).
  * Malformed note JSON -> skip + log, NEVER fail the migration.
  * NEVER remove or rewrite the original `note` (kept for compatibility/audit).

Deterministic summary (printed + returned + logged) - replaces the bench-SQL
count gate (FC has no console; this migration is additive/non-destructive):
  total_scanned, eligible, backfilled, already_populated, malformed,
  skipped (no catalogue note), failures.

`run_backfill` is also a reusable READ-or-WRITE helper (dry_run=1 reports
without writing) - no temporary production counting endpoint needed.
"""
import json

import frappe

# note JSON key -> promoted SKU Catalog field. last_catalogue_sync_at is seeded
# from last_seen_at (old rows predate the field). rsp_price is NOT here.
NOTE_TO_FIELD = (
    ("image_url", "image_url"),
    ("catalogue_price", "catalogue_price"),
    ("sale_price", "sale_price"),
    ("external_stock", "external_stock"),
    ("catalogue_id", "catalogue_id"),
    ("parent_sku", "parent_sku"),
    ("is_variant", "is_variant"),
    ("price_confidence", "price_confidence"),
    # product_status comes from status_name||status_raw (handled specially)
)
PROMOTED_FIELDS = ("image_url", "catalogue_price", "sale_price",
                   "external_stock", "product_status", "catalogue_id",
                   "parent_sku", "is_variant", "price_confidence",
                   "last_catalogue_sync_at")
CATALOGUE_NOTE_MARK = '"src": "catalogue/list"'
BATCH_COMMIT = 500


def _empty(v):
    """A real field is 'empty' (repairable) only when NULL/"". 0 is a valid
    Currency/Int/Check value and is preserved (never treated as empty)."""
    return v in (None, "")


def _derived_values(payload, last_seen_at):
    """Promoted field -> usable value from the parsed note payload (None when
    the note has nothing for that field)."""
    out = {}
    for note_key, field in NOTE_TO_FIELD:
        v = payload.get(note_key)
        if field == "is_variant":
            out[field] = (1 if v else 0) if note_key in payload else None
        else:
            out[field] = v
    out["product_status"] = payload.get("status_name") or payload.get("status_raw")
    # marker seeded from last_seen_at, but does NOT gate other fields (Gate 2)
    out["last_catalogue_sync_at"] = last_seen_at
    return out


def run_backfill(dry_run=0, batch_commit=BATCH_COMMIT, brand=None):
    """FIELD-LEVEL idempotent backfill (Gate 2, 2026-06-13). Each promoted
    field is inspected independently: an EMPTY (NULL/"") real field is filled
    from a usable note value; a POPULATED field is preserved. A partially
    populated row is repairable on rerun (last_catalogue_sync_at being set does
    NOT skip the row). rsp_price is never touched; note is never rewritten;
    malformed note -> skip + log.

    Summary: fully_already_populated, partially_backfilled, newly_backfilled,
    malformed, skipped, failures (+ total_scanned, eligible)."""
    summary = {"total_scanned": 0, "eligible": 0, "newly_backfilled": 0,
               "partially_backfilled": 0, "fully_already_populated": 0,
               "malformed": 0, "skipped": 0, "failures": 0,
               "dry_run": int(dry_run or 0)}
    filters = {"note": ["like", "%" + CATALOGUE_NOTE_MARK + "%"]}
    if brand:
        filters["brand"] = brand
    rows = frappe.get_all(
        "EC Marketplace SKU Catalog", filters=filters,
        fields=["name", "note", "last_seen_at"] + list(PROMOTED_FIELDS),
        limit_page_length=0)
    pending = 0
    for r in rows:
        summary["total_scanned"] += 1
        note = r.get("note")
        if not note or CATALOGUE_NOTE_MARK not in note:
            summary["skipped"] += 1
            continue
        try:
            payload = json.loads(note)
            if not isinstance(payload, dict):
                raise ValueError("note JSON is not an object")
        except Exception:
            summary["malformed"] += 1
            frappe.log_error("malformed note JSON on %s" % r["name"],
                             "alerts.catalogue_backfill")
            continue
        summary["eligible"] += 1
        derived = _derived_values(payload, r.get("last_seen_at"))
        empties = [f for f in PROMOTED_FIELDS if _empty(r.get(f))]
        # "newly" = this row was never backfilled/synced before (marker empty);
        # "partially" = the marker was already set and we are repairing other
        # still-empty fields. (is_variant defaults to 0 so a field-count test is
        # unreliable; the marker is the deterministic signal.)
        marker_was_empty = _empty(r.get("last_catalogue_sync_at"))
        # fill ONLY empty fields that the note can supply a usable value for
        to_set = {f: derived[f] for f in empties if derived.get(f) not in (None, "")}
        if not empties:
            summary["fully_already_populated"] += 1
            continue
        if not to_set:
            # empties exist but the note has nothing to fill them -> nothing to do
            summary["fully_already_populated"] += 1
            continue
        if not dry_run:
            try:
                # NEVER touches rsp_price / note. update_modified=False = audit.
                frappe.db.set_value("EC Marketplace SKU Catalog", r["name"],
                                    to_set, update_modified=False)
                pending += 1
                if pending >= batch_commit:
                    frappe.db.commit()
                    pending = 0
            except Exception:
                summary["failures"] += 1
                frappe.log_error(frappe.get_traceback(),
                                 "alerts.catalogue_backfill set %s" % r["name"])
                continue
        if marker_was_empty:
            summary["newly_backfilled"] += 1
        else:
            summary["partially_backfilled"] += 1
    if not dry_run and pending:
        frappe.db.commit()
    frappe.logger("alerts").info({"catalogue_backfill": summary})
    return summary

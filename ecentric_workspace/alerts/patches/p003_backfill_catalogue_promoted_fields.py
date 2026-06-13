"""Phase 3 (2026-06-13): backfill promoted SKU Catalog fields from note JSON.

Runs AFTER the additive schema sync (the 10 new columns + EC Catalogue Sync
Run exist by the time post_model_sync patches run). Delegates to the
idempotent service so the logic is unit-tested and reusable; imports ONLY the
service (no UI/API module dependency).

Field-level idempotent (Gate 2): per-field empty -> fill from note, populated
-> preserve; never modifies rsp_price; skips malformed note JSON with logging;
keeps the original note. Prints a deterministic summary. Never raises out of
the migration (fail-open at row level inside the service).
"""
from ecentric_workspace.alerts.services import catalogue_backfill


def execute():
    summary = catalogue_backfill.run_backfill()
    print("p003_backfill_catalogue_promoted_fields: %s" % summary)
    return summary

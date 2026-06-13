"""Step 1 (2026-06-13): migrate legacy EC Alert status `Resolved` -> `Closed`.

Decision D1: `Closed` is the canonical completed status. Existing records
created under the old model carry `Resolved`; this patch rewrites them so the
final stored value is `Closed`. `Ignored` is unchanged (still canonical).

Properties:
  * IDEMPOTENT - a re-run finds 0 `Resolved` rows and is a no-op.
  * Reports the affected-row count (printed + returned).
  * Raw SQL UPDATE (bypasses the controller's no-reopen guard; this is a
    same-state terminal->terminal data fix, not a lifecycle transition).
    resolved_by / resolved_at are left intact (Resolved already stamped them).
  * Touches ONLY EC Alert.status. No other table, no schema change here (the
    Select option set is updated in ec_alert.json, synced by bench migrate
    before post_model_sync patches run).

Rollback is NOT automatically safe once this patch has run. After migration
the DB contains `Closed` rows that are now indistinguishable from `Closed`
rows produced by ordinary new handling, and the dropped Select option means
old code paths that wrote/validated `Resolved` no longer round-trip. A safe
rollback therefore requires ONE of:
  (a) compatibility code that keeps reading/writing `Closed` (the enum change
      is additive, but the data is already converted - code revert alone does
      NOT restore the prior state), OR
  (b) a reverse data migration with an explicit discriminator to tell
      newly-Closed from migrated-Resolved (e.g. a recorded migration marker),
      which this patch does not capture, OR
  (c) restoring EC Alert from the pre-migrate backup.
Do not assume a plain code/redeploy rollback reverts the data.
"""
import frappe


def _count_resolved():
    row = frappe.db.sql(
        """SELECT COUNT(*) AS n FROM `tabEC Alert` WHERE status = 'Resolved'""",
        as_dict=True)
    return int(row[0].n) if row else 0


def execute():
    affected = _count_resolved()
    if affected == 0:
        print("p002_migrate_resolved_to_closed: 0 Resolved rows - no-op")
        return {"affected": 0}
    frappe.db.sql(
        """UPDATE `tabEC Alert` SET status = 'Closed' WHERE status = 'Resolved'""")
    frappe.db.commit()
    remaining = _count_resolved()
    print("p002_migrate_resolved_to_closed: migrated %d Resolved -> Closed "
          "(remaining Resolved: %d)" % (affected, remaining))
    return {"affected": affected, "remaining": remaining}

"""One-time maintenance: safely purge KNOWN test / duplicate EC Price Policy records.

This is an ADMIN MAINTENANCE SCRIPT, NOT a product API. It is intentionally NOT
whitelisted and has NO UI button, so the normal permanent-delete guard
(services.policy_validation.delete_decision) stays fully in force for every regular
user. Use this only to clean up specific testing/duplicate records you can name
explicitly; it is not meant to be run routinely.

Usage (DRY-RUN by default — prints the plan, deletes nothing):

    bench --site <site> execute \
        ecentric_workspace.alerts.maintenance.cleanup_test_policies.run \
        --kwargs "{'names': ['EC-PP-00012', 'EC-PP-00031']}"

Execute for real (writes a JSON backup first, then deletes the non-Active rows):

    bench --site <site> execute \
        ecentric_workspace.alerts.maintenance.cleanup_test_policies.run \
        --kwargs "{'names': ['EC-PP-00012'], 'execute': True}"

Safety properties:
  * dry-run by default; deletion requires an explicit execute=True flag
  * refuses any record whose status is currently Active
  * timestamped JSON backup of every doc is written BEFORE deletion
  * System Manager / Administrator only
  * records the deleted names + operator in the returned summary and the Frappe log
  * uses the SUPPORTED Frappe deletion API (frappe.delete_doc) — never raw SQL

Deletion mechanism note: the installed stack is Frappe v15 (see apps; pyproject pins
frappe~=15.0.0). `frappe.delete_doc` is the supported, version-stable document-deletion
entry point across v13–v15 and runs the doctype's own on_trash hooks + link checks, so
no raw SQL is used.
"""
import json
import os

import frappe
from frappe.utils import now_datetime

DOCTYPE = "EC Price Policy"
# Columns printed for every inspected record (dry-run + execute).
SNAPSHOT_FIELDS = ("name", "status", "brand", "platform", "seller_sku",
                   "creation", "modified")


def _require_admin():
    """System Manager / Administrator only. Raises PermissionError otherwise."""
    user = frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return user
    raise frappe.PermissionError(
        "cleanup_test_policies requires the System Manager role (user=%s)" % user)


def _normalize_names(names):
    """Accept a list OR a comma-separated string; drop blanks/whitespace."""
    if isinstance(names, str):
        names = names.split(",")
    return [str(n).strip() for n in (names or []) if str(n).strip()]


def plan_deletions(docs):
    """PURE planner (no DB access). Splits fetched rows into deletable vs
    blocked-because-Active, preserving input order. `docs` is a list of dicts that each
    carry at least name + status. Returns (deletable[list], blocked_active[list])."""
    deletable, blocked = [], []
    for d in docs:
        if (d.get("status") or "") == "Active":
            blocked.append(d)
        else:
            deletable.append(d)
    return deletable, blocked


def run(names=None, execute=False, backup_dir=None):
    """Dry-run (default) or execute a bounded cleanup of named EC Price Policy records.
    Returns a summary dict; prints a human-readable plan for the bench console."""
    operator = _require_admin()
    names = _normalize_names(names)
    if not names:
        print("No names provided. Pass --kwargs \"{'names': ['EC-PP-...']}\".")
        return {"error": "no names provided", "deleted": [], "dry_run": not execute,
                "operator": operator}

    rows, missing = [], []
    for nm in names:
        if frappe.db.exists(DOCTYPE, nm):
            rows.append(frappe.db.get_value(DOCTYPE, nm, SNAPSHOT_FIELDS, as_dict=True))
        else:
            missing.append(nm)
    deletable, blocked = plan_deletions(rows)

    summary = {
        "doctype": DOCTYPE,
        "frappe_version": getattr(frappe, "__version__", "?"),
        "operator": operator,
        "requested": names,
        "missing": missing,
        "blocked_active": [d.get("name") for d in blocked],
        "deletable": [d.get("name") for d in deletable],
        "inspected": [dict(d) for d in rows],
        "dry_run": not execute,
        "deleted": [],
        "backup_file": None,
    }

    # Always print the inspected plan so a dry-run is fully informative.
    for d in rows:
        print("  %-16s status=%-9s brand=%-12s platform=%-8s sku=%-20s created=%s modified=%s" % (
            d.get("name"), d.get("status"), d.get("brand"), d.get("platform"),
            d.get("seller_sku"), d.get("creation"), d.get("modified")))
    if blocked:
        print("REFUSED (currently Active, never purged): %s" % ", ".join(summary["blocked_active"]))
    if missing:
        print("NOT FOUND: %s" % ", ".join(missing))

    if not execute:
        print("DRY-RUN: nothing deleted. Re-run with execute=True to delete %d record(s)."
              % len(deletable))
        return summary
    if not deletable:
        print("Nothing to delete (all requested rows are Active or missing).")
        return summary

    # --- timestamped JSON backup of full docs BEFORE any deletion ---
    backup_dir = backup_dir or frappe.get_site_path("private", "backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = now_datetime().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, "cleanup_ec_price_policy_%s.json" % ts)
    payload = {"doctype": DOCTYPE, "operator": operator, "timestamp": ts,
               "docs": [frappe.get_doc(DOCTYPE, d["name"]).as_dict() for d in deletable]}
    with open(backup_file, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    summary["backup_file"] = backup_file
    print("Backup written: %s" % backup_file)

    # --- delete via the supported Frappe API (never raw SQL) ---
    for d in deletable:
        frappe.delete_doc(DOCTYPE, d["name"], ignore_permissions=True, force=False)
        summary["deleted"].append(d["name"])
    frappe.db.commit()
    frappe.logger("alerts").info(
        "cleanup_test_policies: operator=%s deleted=%s backup=%s"
        % (operator, summary["deleted"], backup_file))
    print("Deleted %d record(s): %s" % (len(summary["deleted"]), ", ".join(summary["deleted"])))
    return summary

"""Step 6 - Price Setup lifecycle wiring (2026-06-14). When an EC Price Policy
becomes Active (create / edit / status change / import), auto-terminalize the
brand's ACTIVE missing_policy alerts that are NOW covered by an Active policy,
then recompute the brand's aggregated Setup ToDo ONCE.

Bindings:
  * acts ONLY for status == 'Active' (Draft/Paused/Inactive do nothing). A
    deactivated policy never reopens an alert - the engine raises a fresh one
    later if coverage lapses.
  * a candidate alert is closed iff the AUTHORITATIVE policy_lookup.find_policy
    on the alert's OWN scope (brand, platform, shop, item, seller_sku + current
    effective time) now returns SOME Active policy - not necessarily the one
    just saved. Audit records the REAL matched policy.
  * terminalize via the canonical INTERNAL transition (case_lifecycle guard +
    the EC Alert controller's _stamp_resolution / _guard_no_reopen) - NO
    whitelisted-API/HTTP round-trip. Note: 'Auto-closed: covered by active
    price policy <policy>'. resolved_by/resolved_at stamped by the controller;
    a timeline Comment is the audit trail. Idempotent: an already-terminal
    alert is skipped.
  * recompute the aggregated Setup ToDo ONCE per affected brand
    (case_todo.sync_brand_setup); the per-row controller autosync is suspended
    during the close loop so it runs exactly once.
  * The close step does NOT swallow errors - it propagates so the CALLER can
    enforce the transaction policy (single save -> rollback; bulk -> savepoint).
    Only the ToDo recompute is best-effort fail-open (case_todo's own design;
    a stale ToDo self-corrects on the next alert event, never corrupts data).
"""
import frappe

from ecentric_workspace.alerts.services import case_lifecycle as cl
from ecentric_workspace.alerts.services import case_todo
from ecentric_workspace.alerts.services import policy_lookup

_CLOSE_STATUS = "Closed"
ACTIVE = "Active"


def _row_value(row, field, default=None):
    """Read `field` from an alert row regardless of its concrete type: a dict, a
    frappe._dict (what frappe.get_all returns in production - has .get), a Frappe
    Document / arbitrary object, or a plain SimpleNamespace (the unit-test
    fixture). Never assumes the row supports .get or item access."""
    if isinstance(row, dict):
        return row.get(field, default)
    getter = getattr(row, "get", None)
    if callable(getter):
        try:
            return getter(field, default)
        except TypeError:                 # a .get that takes no default arg
            value = getter(field)
            return default if value is None else value
    return getattr(row, field, default)


def terminalize_for_policy(policy, actor=None, recompute=True):
    """`policy`: an EC Price Policy doc (or its name). Returns a lifecycle
    summary {brand, policy, policy_status, scanned, closed:[{alert,
    matched_policy}], skipped_no_coverage}. No-op summary unless Active.
    recompute=True recomputes the brand Setup ToDo here (single save/status);
    bulk import passes recompute=False and recomputes ONCE per brand at the end."""
    doc = policy if hasattr(policy, "status") else frappe.get_doc("EC Price Policy", policy)
    summary = {"brand": doc.brand, "policy": doc.name, "policy_status": doc.status,
               "scanned": 0, "closed": [], "skipped_no_coverage": 0}
    if (doc.status or "") != ACTIVE or not doc.brand:
        return summary
    actor = actor or frappe.session.user

    candidates = frappe.get_all(
        "EC Alert",
        filters={"brand": doc.brand, "rule_code": "missing_policy",
                 "status": ["in", list(cl.ACTIVE_STATUSES)]},
        fields=["name", "platform", "shop", "item", "seller_sku", "status"])
    summary["scanned"] = len(candidates)

    affected = False
    # one aggregated ToDo recompute for the brand: suppress the per-alert
    # controller autosync while we close, then recompute once below.
    with case_todo.autosync_suspended():
        for a in candidates:
            matched, _level = policy_lookup.find_policy(
                doc.brand, _row_value(a, "platform"), _row_value(a, "shop"),
                _row_value(a, "item"), _row_value(a, "seller_sku"))
            if not matched:
                summary["skipped_no_coverage"] += 1
                continue
            nm = _row_value(a, "name")
            _close_alert(nm, matched.name, actor)
            summary["closed"].append({"alert": nm, "matched_policy": matched.name})
            affected = True

    if affected and recompute:
        _recompute_setup(doc.brand)
    # remaining distinct active missing_policy SKUs for the brand (UI feedback)
    try:
        summary["remaining_missing"] = case_todo.remaining_missing_skus(doc.brand)
    except Exception:
        summary["remaining_missing"] = None
    return summary


def _close_alert(alert_name, matched_policy, actor):
    """Canonical internal terminalize -> Closed (idempotent). Same guards as the
    API path (case_lifecycle.can_transition + controller stamp/guards) but
    WITHOUT the whitelisted endpoint. Errors propagate to the caller."""
    doc = frappe.get_doc("EC Alert", alert_name)
    if cl.is_terminal(doc.status):
        return  # idempotent
    if not cl.can_transition(doc.status, _CLOSE_STATUS):
        return
    note = "Auto-closed: covered by active price policy %s" % matched_policy
    doc.status = _CLOSE_STATUS
    doc.resolution_note = note
    doc.save(ignore_permissions=True)   # controller stamps resolved_by/resolved_at
    try:
        doc.add_comment("Comment", "%s (by %s)" % (note, actor))
    except Exception:
        pass


def _recompute_setup(brand):
    """Recompute the brand's aggregated Setup ToDo ONCE. Fail-open: a ToDo glitch
    must never roll back a correct policy save + alert close."""
    try:
        case_todo.sync_brand_setup(brand)
    except Exception:
        frappe.log_error(frappe.get_traceback(),
                         "alerts.policy_setup._recompute_setup %s" % brand)

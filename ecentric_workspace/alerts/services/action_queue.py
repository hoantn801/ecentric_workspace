"""EC Alert Action queue - creation + DRY-RUN processing.

ARCHITECTURE RULE (approved): Price Check -> EC Alert -> EC Alert Action ->
(background) execution. This module contains NO HTTP CLIENT and NO IMPORT of
any HTTP library. Real Omisell execution does not exist in Phase C - the
processing step can only end in: Skipped / Dry Run.

Lock action is created ONLY when ALL hold (rule 7, Phase C scope):
  * winning rule in LOCKABLE_RULES
  * policy.enable_stock_safety_lock = 1
  * baseline confidence High or Medium
  * dedupe: no existing action with same dedupe_key (unique index = backstop)
  * active EC Automation Pause -> action row IS created but status=Skipped
    (audit trail of the suppressed lock; alert itself always created)
"""
import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime, nowdate

from . import dedupe_keys

LOCKABLE_RULES = ("possible_missing_zero", "severe_price_drop")
HIGH_CONFIDENCE = ("High", "Medium")


def maybe_create_lock_action(alert_name, log, line, policy, confidence, rule_code):
    """Returns (outcome, action_name_or_None). Pure decision + insert, no API."""
    if rule_code not in LOCKABLE_RULES:
        return "rule_not_lockable", None
    if not int(policy.enable_stock_safety_lock or 0):
        return "policy_lock_disabled", None
    if confidence not in HIGH_CONFIDENCE:
        return "low_confidence", None

    key = dedupe_keys.lock_action_key(log.external_order_id, line.external_line_id, rule_code)
    if frappe.db.exists("EC Alert Action", {"dedupe_key": key}):
        return "deduped", None

    pause = find_active_pause(log.brand, log.platform, log.shop, line.item, line.seller_sku)
    minutes = int(policy.stock_lock_duration_minutes or 120)
    doc = frappe.get_doc({
        "doctype": "EC Alert Action",
        "alert": alert_name,
        "action_type": "Stock Safety Lock",
        "status": "Skipped" if pause else "Pending",
        "source_system": "Omisell",
        "brand": log.brand,
        "platform": log.platform,
        "shop": log.shop,
        "item": line.item,
        "seller_sku": line.seller_sku,
        "external_product_id": line.external_product_id,
        "lock_until": add_to_date(now_datetime(), minutes=minutes),
        "lock_reason": "%s: unit price %s vs reference %s (policy %s, confidence %s)" % (
            rule_code, line.unit_check_price, line.baseline_price_at_check or line.min_price_at_check,
            policy.name, confidence),
        "requested_at": now_datetime(),
        "dedupe_key": key,
        "error_message": ("Skipped at creation: active EC Automation Pause %s" % pause) if pause else None,
    })
    doc.insert(ignore_permissions=True)
    return ("skipped_pause" if pause else "created"), doc.name


def find_active_pause(brand, platform=None, shop=None, item=None, seller_sku=None):
    """Brand-scoped pause match (a pause for Brand A never affects Brand B).
    A pause row matches when every field it specifies agrees with the target;
    expired-but-still-Active rows are treated as inactive (scheduler will flip
    them in a later phase)."""
    if not brand:
        return None
    now = now_datetime()
    rows = frappe.get_all(
        "EC Automation Pause",
        filters={"brand": brand, "status": "Active", "automation_type": "Stock Safety Lock"},
        fields=["name", "platform", "shop", "item", "seller_sku", "pause_from", "pause_until"],
    )
    for r in rows:
        if r.pause_from and r.pause_from > now:
            continue
        if r.pause_until and r.pause_until < now:
            continue
        if r.platform and r.platform != "All" and platform and r.platform != platform:
            continue
        if r.shop and r.shop != shop:
            continue
        if r.item and r.item != item:
            continue
        if r.seller_sku and r.seller_sku != seller_sku:
            continue
        return r.name
    return None


def process_pending_actions(limit=100):
    """Dry-run era worker. Guard chain per action: pause re-check ->
    per-brand credential -> dry-run stamp. One failure never kills the batch."""
    summary = {"processed": 0, "dry_run": 0, "skipped_pause": 0,
               "skipped_credential": 0, "skipped_not_implemented": 0, "errors": 0}
    names = frappe.get_all(
        "EC Alert Action",
        filters={"status": "Pending", "action_type": "Stock Safety Lock"},
        pluck="name", limit=limit, order_by="creation asc",
    )
    for name in names:
        try:
            outcome = _process_one(name)
            summary["processed"] += 1
            summary[outcome] += 1
        except Exception:
            summary["errors"] += 1
            frappe.log_error(frappe.get_traceback(), "alerts.action_queue.process %s" % name)
    return summary


def _process_one(name):
    a = frappe.get_doc("EC Alert Action", name)

    # final guard 1: pause re-check
    pause = find_active_pause(a.brand, a.platform, a.shop, a.item, a.seller_sku)
    if pause:
        a.status = "Skipped"
        a.error_message = "Skipped at processing: active EC Automation Pause %s" % pause
        a.save(ignore_permissions=True)
        return "skipped_pause"

    # final guard 2: per-brand credential (no cross-brand reuse, ever)
    bis = frappe.db.get_value(
        "EC Brand Integration Settings",
        {"brand": a.brand, "integration_type": "Omisell"},
        ["name", "enabled", "credential_status", "dry_run_stock_lock"],
        as_dict=True,
    )
    if not bis or not int(bis.enabled or 0) or bis.credential_status != "Active":
        a.status = "Skipped"
        a.error_message = ("No active Omisell integration credential for brand %s "
                           "(EC Brand Integration Settings missing/disabled/inactive)." % a.brand)
        a.save(ignore_permissions=True)
        _upsert_credential_alert(a)
        return "skipped_credential"

    # final guard 3: dry-run stamp. NOTE: there is intentionally no 'else'
    # branch that calls Omisell - no HTTP client exists in Phase C.
    if int(bis.dry_run_stock_lock or 0):
        a.status = "Dry Run"
        a.executed_at = now_datetime()
        a.executed_by = frappe.session.user
        a.api_response = ("DRY RUN: would set/increase Omisell BUFFER STOCK to lock "
                          "the sellable quantity until %s (available -> 0, physical "
                          "stock untouched - decision DS1). No API was called." % a.lock_until)
        a.save(ignore_permissions=True)
        return "dry_run"

    a.status = "Skipped"
    a.error_message = ("Real stock lock execution is not implemented in Phase C "
                       "(dry_run_stock_lock=0 but no executor exists yet).")
    a.save(ignore_permissions=True)
    return "skipped_not_implemented"


def _upsert_credential_alert(action):
    yyyymmdd = nowdate().replace("-", "")
    key = dedupe_keys.missing_credential_key(action.brand, yyyymmdd)
    if frappe.db.exists("EC Alert", {"dedupe_key": key}):
        return
    from . import brand_resolver
    frappe.get_doc({
        "doctype": "EC Alert",
        "alert_type": "Price Compliance",
        "rule_code": "missing_integration_credential",
        "severity": "Warning",
        "status": "Open",
        "title": "Missing Omisell credential for brand %s" % action.brand,
        "message": ("Stock Safety Lock action %s was skipped because no active "
                    "EC Brand Integration Settings exists for this brand." % action.name),
        "brand": action.brand,
        "platform": action.platform,
        "shop": action.shop,
        "owner_user": brand_resolver.resolve_owner(action.shop, action.brand),
        "source_system": "Omisell",
        "reference_doctype": "EC Alert Action",
        "reference_name": action.name,
        "recommended_action": "Notify Only",
        "dedupe_key": key,
        "detected_at": now_datetime(),
    }).insert(ignore_permissions=True)

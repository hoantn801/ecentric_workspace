"""Orchestrator: per-line price check -> EC Alert (+ lock action via
action_queue). Single DB transaction context, NO HTTP anywhere (hard rules
11/12: the Omisell API is never called from the price-check path).

Flow per 04_PHASE_C_DESIGN s3 with decisions C1 (dual-tier dedupe) and C2
(single winning rule per line).
"""
import frappe
from frappe.utils import now_datetime, nowdate

from . import (action_queue, baseline as baseline_mod, brand_resolver,
               dedupe_keys, policy_lookup, pricing, rules)

CHECK_RESULT_LABEL = {
    "possible_missing_zero": "Possible Missing Zero",
    "severe_price_drop": "Severe Price Drop",
    "below_min": "Below Min",
    "above_high": "Above High",
}

# alert_type mapping: anomaly = statistical deviation; compliance = policy/master data
ALERT_TYPE = {
    "possible_missing_zero": "Price Anomaly",
    "severe_price_drop": "Price Anomaly",
    "above_high": "Price Anomaly",
    "below_min": "Price Compliance",
    "missing_policy": "Price Compliance",
    "missing_brand_mapping": "Price Compliance",
}


def check_order_log(order_log_name, raw_shop_id=None):
    """Run the rules engine over every line of one EC Marketplace Order Log.
    raw_shop_id: original Omisell shop id from the payload - used only in
    missing_brand_mapping dedupe keys when no EC Marketplace Shop resolved.
    Returns a summary dict. Idempotent: dedupe keys make re-runs no-ops."""
    log = frappe.get_doc("EC Marketplace Order Log", order_log_name)
    s = {"order": log.name, "lines": len(log.items), "alerts_created": 0,
         "alerts_deduped": 0, "actions": {}, "ok": 0, "unpriced": 0}
    yyyymmdd = nowdate().replace("-", "")

    if not log.brand:
        # Missing brand mapping: warning alert (daily SKU-level dedupe, C1),
        # NO policy check, NO stock lock. (Approved rule 1.)
        for line in log.items:
            price, _src = pricing.compute_unit_check_price(line.as_dict())
            if price is not None:
                line.unit_check_price = price
            key = dedupe_keys.missing_brand_mapping_key(
                log.platform, raw_shop_id or log.shop, line.seller_sku, yyyymmdd,
                external_product_id=None)
            created = _create_alert(
                log, line, rule_code="missing_brand_mapping", severity="Warning",
                dedupe_key=key, price=price, policy=None, baseline=None, gap=None,
                recommended_action="Notify Only",
                title="Missing brand mapping: shop %s / SKU %s" % (
                    raw_shop_id or log.shop or "?", line.seller_sku or "?"),
                message=("Order %s (%s) could not be resolved to a brand. "
                         "Map this shop in EC Marketplace Shop. Price policy check "
                         "and Stock Safety Lock were NOT run.") % (
                             log.external_order_id, log.platform))
            s["alerts_created" if created else "alerts_deduped"] += 1
            line.check_result = "Missing Brand Mapping"
        log.sync_status = "Success"
        log.save(ignore_permissions=True)
        return s

    for line in log.items:
        price, _src = pricing.compute_unit_check_price(line.as_dict())
        if price is None:
            s["unpriced"] += 1
            continue
        line.unit_check_price = price

        policy, level = policy_lookup.find_policy(
            log.brand, log.platform, log.shop, line.item, line.seller_sku)
        if not policy:
            key = dedupe_keys.missing_policy_key(
                log.brand, log.platform, log.shop, line.seller_sku, yyyymmdd,
                external_product_id=None)
            created = _create_alert(
                log, line, rule_code="missing_policy", severity="Warning",
                dedupe_key=key, price=price, policy=None, baseline=None, gap=None,
                recommended_action="Notify Only",
                title="Missing price policy: %s / %s" % (log.brand, line.seller_sku or line.item),
                message=("No active EC Price Policy matched brand %s, platform %s, "
                         "shop %s, SKU %s. Create one to enable price checking.") % (
                             log.brand, log.platform, log.shop, line.seller_sku or line.item))
            s["alerts_created" if created else "alerts_deduped"] += 1
            line.check_result = "Missing Rule"
            continue

        line.min_price_at_check = policy.min_price
        base, confidence, _bsrc = baseline_mod.get_baseline(
            log.brand, log.platform, log.shop, line.item, line.seller_sku,
            policy={"reference_price": policy.reference_price, "min_price": policy.min_price},
            exclude_order_log=log.name)
        line.baseline_price_at_check = base

        hit = rules.evaluate(price, {
            "min_price": policy.min_price,
            "high_alert_percent": policy.high_alert_percent,
            "severe_drop_percent": policy.severe_drop_percent,
        }, base)

        if not hit:
            line.check_result = "OK"
            s["ok"] += 1
            continue

        rule_code = hit["rule_code"]
        line.check_result = CHECK_RESULT_LABEL[rule_code]
        key = dedupe_keys.price_alert_key(log.external_order_id, line.external_line_id, rule_code)
        alert_name, created = _create_alert(
            log, line, rule_code=rule_code, severity=hit["severity"],
            dedupe_key=key, price=price, policy=policy, baseline=base,
            gap=hit["gap_percent"], recommended_action=hit["recommended_action"],
            title="%s: %s @ %s (ref %s)" % (
                CHECK_RESULT_LABEL[rule_code], line.seller_sku or line.item,
                frappe.format_value(price, {"fieldtype": "Currency"}),
                frappe.format_value(hit["reference_price"], {"fieldtype": "Currency"})),
            message=("Order %s line %s: unit price %s, min %s, baseline %s (%s), "
                     "gap %s%%. Policy %s (level %s).") % (
                         log.external_order_id, line.external_line_id, price,
                         policy.min_price, base, confidence, hit["gap_percent"],
                         policy.name, level),
            return_name=True)
        s["alerts_created" if created else "alerts_deduped"] += 1

        outcome, _action = action_queue.maybe_create_lock_action(
            alert_name, log, line, policy, confidence, rule_code)
        s["actions"][outcome] = s["actions"].get(outcome, 0) + 1

    log.sync_status = "Success"
    log.save(ignore_permissions=True)
    return s


def _create_alert(log, line, rule_code, severity, dedupe_key, price, policy,
                  baseline, gap, recommended_action, title, message,
                  return_name=False):
    """Dedupe-then-insert. Existence of the dedupe_key (ANY status) blocks
    re-creation - the unique index enforces this anyway; Open/In Review is the
    spec rule, and a Resolved alert for the same key means the same incident
    was already handled (re-syncs must not reopen it)."""
    existing = frappe.db.get_value("EC Alert", {"dedupe_key": dedupe_key}, "name")
    if existing:
        return (existing, False) if return_name else False
    doc = frappe.get_doc({
        "doctype": "EC Alert",
        "alert_type": ALERT_TYPE[rule_code],
        "rule_code": rule_code,
        "severity": severity,
        "status": "Open",
        "title": title[:140],
        "message": message,
        "brand": log.brand or None,
        "platform": log.platform,
        "shop": log.shop,
        "item": line.item,
        "seller_sku": line.seller_sku,
        "owner_user": brand_resolver.resolve_owner(log.shop, log.brand),
        "source_system": log.source_system or "Omisell",
        "reference_doctype": "EC Marketplace Order Log",
        "reference_name": log.name,
        "actual_price": price,
        "min_price": getattr(policy, "min_price", None) if policy else None,
        "baseline_price": baseline,
        "gap_percent": gap,
        "recommended_action": recommended_action,
        "dedupe_key": dedupe_key,
        "detected_at": now_datetime(),
    })
    doc.insert(ignore_permissions=True)
    return (doc.name, True) if return_name else True

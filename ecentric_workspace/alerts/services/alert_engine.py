"""Orchestrator: per-line price check -> EC Alert (+ lock action via
action_queue). Single DB transaction context, NO HTTP anywhere (hard rules
11/12: the Omisell API is never called from the price-check path).

Flow per 04_PHASE_C_DESIGN s3 with decisions C1 (dual-tier dedupe) and C2
(single winning rule per line).
"""
import frappe
from frappe.utils import now_datetime, nowdate

from . import (action_queue, baseline as baseline_mod, brand_resolver,
               dedupe_keys, policy_lookup, pricing, rule_overlay, rules)

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
                log.platform, raw_shop_id or log.omisell_shop_id or log.shop,
                line.seller_sku, yyyymmdd,
                external_product_id=line.external_product_id)
            created = _create_alert(
                log, line, rule_code="missing_brand_mapping", severity="Warning",
                dedupe_key=key, price=price, policy=None, baseline=None, gap=None,
                recommended_action="Notify Only",
                title="Missing brand mapping: shop %s / SKU %s" % (
                    raw_shop_id or log.omisell_shop_id or log.shop or "?",
                    line.seller_sku or "?"),
                message=("Order %s (%s) could not be resolved to a brand. "
                         "Map this shop in EC Marketplace Shop. Price policy check "
                         "and Stock Safety Lock were NOT run.") % (
                             log.external_order_id, log.platform))
            s["alerts_created" if created else "alerts_deduped"] += 1
            line.check_result = "Missing Brand Mapping"
        log.sync_status = "Success"
        log.save(ignore_permissions=True)
        return s

    flags = _brand_price_flags(log.brand)
    for line in log.items:
        ev = pricing.evaluate_components(line.as_dict(), flags)
        price = ev["effective_check_price"]
        if price is None:
            s["unpriced"] += 1
            continue
        # G1.1 component-basis audit snapshot on the order line
        line.unit_check_price = price            # legacy alias
        line.effective_check_price = price
        line.price_components_used = ev["price_components_used"]
        if ev.get("customer_paid_price") is not None:
            line.customer_paid_price = ev["customer_paid_price"]

        policy, level = policy_lookup.find_policy(
            log.brand, log.platform, log.shop, line.item, line.seller_sku)
        if not policy:
            key = dedupe_keys.missing_policy_key(
                log.brand, log.platform, log.shop, line.seller_sku, yyyymmdd,
                external_product_id=line.external_product_id)
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

        # Phase F rule-config overlay - rules_map == {} (the default when no
        # Active EC Alert Rule matches) keeps everything byte-identical.
        rules_map = rule_overlay.find_rules(
            log.brand, log.platform, log.shop, line.item, line.seller_sku)
        params = rule_overlay.overlay_params({
            "min_price": policy.min_price,
            "high_alert_percent": policy.high_alert_percent,
            "severe_drop_percent": policy.severe_drop_percent,
        }, rules_map)
        hit = rule_overlay.overlay_hit(rules.evaluate(price, params, base), rules_map)

        if not hit:
            line.check_result = "OK"
            s["ok"] += 1
            continue

        rule_code = hit["rule_code"]
        line.check_result = CHECK_RESULT_LABEL[rule_code]
        # G1.1: two-tier - one immutable Occurrence per order line (evidence) +
        # an upserted Case (EC Alert) per brand+sku+rule that KAM works.
        occ_name, created, case_name = _record_price_violation(
            log, line, rule_code, hit, price, ev, policy, base, confidence, level)
        s["alerts_created" if created else "alerts_deduped"] += 1

        if created and rule_overlay.lock_narrowing(rule_code, rules_map):
            outcome, _action = action_queue.maybe_create_lock_action(
                case_name, log, line, policy, confidence, rule_code)
        elif created:
            outcome = ("rule_config_disabled_lock"
                       if rule_code in rule_overlay.LOCKABLE_RULES else "rule_not_lockable")
        else:
            outcome = "occurrence_deduped"
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


# --- G1.1: price-basis config + Case/Occurrence evidence model --------------

def _brand_price_flags(brand):
    """Per-brand component include-flags from EC Brand Alert Config; defaults to
    seller-funded (pricing.DEFAULT_FLAGS) when no row exists. Fail-safe."""
    if not brand:
        return dict(pricing.DEFAULT_FLAGS)
    try:
        row = frappe.db.get_value(
            "EC Brand Alert Config", {"brand": brand},
            list(pricing.COMPONENT_FLAGS), as_dict=True)
    except Exception:
        row = None
    if not row:
        return dict(pricing.DEFAULT_FLAGS)
    return {k: int(row.get(k) or 0) for k in pricing.COMPONENT_FLAGS}


def _record_price_violation(log, line, rule_code, hit, price, ev, policy, base,
                            confidence, level):
    """Insert one immutable EC Alert Occurrence (per order line) and upsert its
    Case (EC Alert per brand+sku+rule while open). Returns
    (occurrence_name, created_bool, case_name). Re-pull of the same line is a
    no-op (occurrence dedupe) and does NOT touch a resolved Case."""
    occ_key = dedupe_keys.occurrence_key(
        log.external_order_id, line.external_line_id, rule_code)
    existing = frappe.db.get_value(
        "EC Alert Occurrence", {"dedupe_key": occ_key}, ["name", "case"], as_dict=True)
    if existing:
        return existing.name, False, existing.case

    case_name, case_created = _find_or_create_case(
        log, line, rule_code, hit, price, ev, policy, base, confidence, level)

    now = now_datetime()
    occ = frappe.get_doc({
        "doctype": "EC Alert Occurrence",
        "case": case_name,
        "rule_code": rule_code,
        "severity": hit["severity"],
        "brand": log.brand or None,
        "platform": log.platform,
        "shop": log.shop,
        "seller_sku": line.seller_sku,
        "item": line.item,
        "product_name": line.product_name,
        "external_order_id": log.external_order_id,
        "external_line_id": line.external_line_id,
        "order_datetime": log.order_datetime,
        "order_status": log.order_status,
        "reference_doctype": "EC Marketplace Order Log",
        "reference_name": log.name,
        "detected_at": now,
        "rsp_price": ev.get("rsp_price"),
        "seller_discount_amount": ev.get("seller_discount_amount"),
        "seller_voucher_amount": ev.get("seller_voucher_amount"),
        "platform_discount_amount": ev.get("platform_discount_amount"),
        "platform_voucher_amount": ev.get("platform_voucher_amount"),
        "customer_paid_price": ev.get("customer_paid_price"),
        "effective_check_price": price,
        "price_components_used": ev["price_components_used"],
        "min_price_at_check": getattr(policy, "min_price", None),
        "baseline_price_at_check": base,
        "gap_percent": hit["gap_percent"],
        "dedupe_key": occ_key,
    })
    occ.insert(ignore_permissions=True)
    _bump_case(case_name, hit, price, ev, now, case_created)
    return occ.name, True, case_name


def _find_or_create_case(log, line, rule_code, hit, price, ev, policy, base,
                         confidence, level):
    """One open Case per brand+seller_sku+rule_code. Returns (name, created)."""
    open_case = frappe.db.get_value("EC Alert", {
        "brand": log.brand, "seller_sku": line.seller_sku, "rule_code": rule_code,
        "status": ["in", ["Open", "In Review"]]}, "name")
    if open_case:
        return open_case, False
    case_key = dedupe_keys._fit("case|%s|%s|%s|%s|%s" % (
        dedupe_keys._s(log.brand), dedupe_keys._s(line.seller_sku),
        dedupe_keys._s(rule_code), dedupe_keys._s(log.external_order_id),
        dedupe_keys._s(line.external_line_id)))
    doc = frappe.get_doc({
        "doctype": "EC Alert",
        "alert_type": ALERT_TYPE[rule_code],
        "rule_code": rule_code,
        "severity": hit["severity"],
        "status": "Open",
        "title": ("%s: %s (min %s)" % (
            CHECK_RESULT_LABEL[rule_code], line.seller_sku or line.item,
            frappe.format_value(getattr(policy, "min_price", None) or 0,
                                {"fieldtype": "Currency"})))[:140],
        "message": ("Case for brand %s / SKU %s / rule %s. Each violating order "
                    "line is an EC Alert Occurrence (evidence). Policy %s (level %s)."
                    % (log.brand, line.seller_sku or line.item, rule_code,
                       getattr(policy, "name", "-"), level)),
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
        "min_price": getattr(policy, "min_price", None),
        "baseline_price": base,
        "gap_percent": hit["gap_percent"],
        "recommended_action": hit["recommended_action"],
        "effective_check_price": price,
        "price_components_used": ev["price_components_used"],
        "occurrence_count": 0,
        "dedupe_key": case_key,
        "detected_at": now_datetime(),
    })
    doc.insert(ignore_permissions=True)
    return doc.name, True


def _bump_case(case_name, hit, price, ev, now, case_created):
    case = frappe.get_doc("EC Alert", case_name)
    case.occurrence_count = int(case.occurrence_count or 0) + 1
    if case_created or not case.first_seen_at:
        case.first_seen_at = now
    case.last_seen_at = now
    g = float(hit.get("gap_percent") or 0)
    if g > float(case.worst_gap_percent or 0):
        case.worst_gap_percent = g
    case.effective_check_price = price
    case.price_components_used = ev["price_components_used"]
    case.actual_price = price
    case.gap_percent = hit.get("gap_percent")
    case.save(ignore_permissions=True)

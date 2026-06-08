"""Phase F rule-config overlay. GOLDEN GUARANTEE: with no Active matching
EC Alert Rule rows, engine behavior is BYTE-IDENTICAL to pre-F production
(apply() returns inputs unchanged; lookup returning {} is the default path).

Scope priority when picking the rule row per rule_code (mirrors policy
lookup): seller_sku/item match > shop match > platform match > brand-wide.
Hard action matrix is NOT widenable here: recommend_stock_lock only NARROWS
(lock still requires policy.enable_stock_safety_lock) and is ignored for
non-lockable rules. severity/threshold overrides apply per matched rule_code.
"""
import frappe

LOCKABLE_RULES = ("severe_price_drop", "possible_missing_zero")


def find_rules(brand, platform=None, shop=None, item=None, seller_sku=None, on_date=None):
    """Returns {rule_code: best_matching_rule_dict}. {} when nothing matches
    (the default, golden path)."""
    if not brand:
        return {}
    on_date = str(on_date or frappe.utils.nowdate())
    try:
        rows = frappe.get_all(
            "EC Alert Rule",
            filters={"brand": brand, "status": "Active", "enabled": 1},
            fields=["name", "rule_code", "platform", "shop", "item", "seller_sku",
                    "severity_override", "threshold_percent",
                    "recommend_stock_lock", "effective_from", "effective_to"],
            limit_page_length=200)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "alerts.rule_overlay.find_rules")
        return {}  # fail-safe: config trouble must never change engine behavior
    best = {}
    for r in rows:
        if r.effective_from and str(r.effective_from) > on_date:
            continue
        if r.effective_to and str(r.effective_to) < on_date:
            continue
        score = _match_score(r, platform, shop, item, seller_sku)
        if score is None:
            continue
        cur = best.get(r.rule_code)
        if not cur or score > cur[0]:
            best[r.rule_code] = (score, r)
    return {code: pair[1] for code, pair in best.items()}


def _match_score(r, platform, shop, item, seller_sku):
    """None = no match. Higher = more specific (SKU 8 > shop 4 > platform 2 > brand 1)."""
    score = 1
    if r.platform and r.platform != "All":
        if not platform or r.platform != platform:
            return None
        score += 2
    if r.shop:
        if not shop or r.shop != shop:
            return None
        score += 4
    if r.seller_sku or r.item:
        sku_ok = r.seller_sku and seller_sku and r.seller_sku == seller_sku
        item_ok = r.item and item and r.item == item
        if not (sku_ok or item_ok):
            return None
        score += 8
    return score


def overlay_params(params, rules_map):
    """Adjust rules.evaluate() parameters from matched rule rows. PURE.
    Unmatched -> params returned unchanged (same dict contents)."""
    if not rules_map:
        return params
    out = dict(params)
    r = rules_map.get("severe_price_drop")
    if r and r.get("threshold_percent"):
        out["severe_drop_percent"] = float(r["threshold_percent"])
    r = rules_map.get("above_high")
    if r and r.get("threshold_percent"):
        out["high_alert_percent"] = float(r["threshold_percent"])
    return out


def overlay_hit(hit, rules_map):
    """Post-process the winning hit. PURE. No matching row -> hit unchanged.

    below_min special case (approved examples): a below_min rule row with
    threshold_percent escalates: gap >= X% under min -> Critical, else the
    severity_override (or Warning when an override-less escalation row
    exists). No row -> stays the engine default (Critical)."""
    if not hit or not rules_map:
        return hit
    r = rules_map.get(hit["rule_code"])
    if not r:
        return hit
    out = dict(hit)
    if hit["rule_code"] == "below_min" and r.get("threshold_percent"):
        if float(hit.get("gap_percent") or 0) >= float(r["threshold_percent"]):
            out["severity"] = "Critical"
        else:
            out["severity"] = r.get("severity_override") or "Warning"
    elif r.get("severity_override"):
        out["severity"] = r["severity_override"]
    return out


def lock_narrowing(rule_code, rules_map):
    """Returns False when a matched rule row explicitly disables the lock
    recommendation for a lockable rule. True = keep engine default
    (policy.enable_stock_safety_lock still required downstream). PURE.
    Never widens; never applies to non-lockable rules."""
    if rule_code not in LOCKABLE_RULES:
        return False  # hard matrix: never lockable regardless of config
    r = (rules_map or {}).get(rule_code)
    if not r:
        return True  # no config -> engine default path
    return bool(int(r.get("recommend_stock_lock") or 0))

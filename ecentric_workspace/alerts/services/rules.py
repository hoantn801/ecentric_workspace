"""Rule D - price rule evaluation. PURE module (no frappe, no DB, no I/O).

Decision C2 (2026-06-07): exactly ONE winning rule per order line.
Priority: possible_missing_zero > severe_price_drop > below_min > above_high > OK.
recommended_action follows the winning rule only.

Action matrix (hard rule - high price NEVER locks stock):
  possible_missing_zero -> Critical + recommend Stock Safety Lock
  severe_price_drop     -> Critical + recommend Stock Safety Lock
  below_min             -> Critical + Notify Only
  above_high            -> Warning  + Notify Only
Eligibility for an actual lock action (policy flag, confidence, pause) is
decided later in action_queue - NOT here.
"""

# "actual_price x 10 is within +/-10-15% of baseline" (spec). We implement the
# widest approved band, 15%, as a single named constant.
MISSING_ZERO_TOLERANCE = 0.15

DEFAULT_SEVERE_DROP_PERCENT = 70.0

# absolute epsilon for threshold comparisons - avoids binary-float artifacts
# (e.g. 99000*0.3 == 29700.000000000004) making exact-at-threshold prices hit
EPSILON = 1e-6

LOCK_RECOMMENDED_RULES = ("possible_missing_zero", "severe_price_drop")


def evaluate(unit_price, policy, baseline_price):
    """unit_price: float > 0. policy: dict(min_price, high_alert_percent,
    severe_drop_percent). baseline_price: float or None.
    Returns winning hit dict(rule_code, severity, recommended_action,
    gap_percent, reference_price) or None (= OK)."""
    if not unit_price or unit_price <= 0:
        return None
    min_price = _f(policy.get("min_price"))
    high_pct = _f(policy.get("high_alert_percent"))
    severe_pct = _f(policy.get("severe_drop_percent")) or DEFAULT_SEVERE_DROP_PERCENT
    baseline = _f(baseline_price)

    # 1. possible_missing_zero
    if baseline and baseline > 0 and unit_price < baseline:
        if abs(unit_price * 10.0 - baseline) <= MISSING_ZERO_TOLERANCE * baseline:
            return _hit("possible_missing_zero", "Critical", "Stock Safety Lock",
                        _drop_gap(unit_price, baseline), baseline)

    # 2. severe_price_drop
    if baseline and baseline > 0:
        threshold = baseline * (1.0 - severe_pct / 100.0)
        if unit_price < threshold - EPSILON:
            return _hit("severe_price_drop", "Critical", "Stock Safety Lock",
                        _drop_gap(unit_price, baseline), baseline)

    # 3. below_min
    if min_price and min_price > 0 and unit_price < min_price:
        return _hit("below_min", "Critical", "Notify Only",
                    _drop_gap(unit_price, min_price), min_price)

    # 4. above_high (vs baseline first, else min_price)
    high_base = baseline if (baseline and baseline > 0) else min_price
    if high_pct and high_pct > 0 and high_base and high_base > 0:
        if unit_price > high_base * (1.0 + high_pct / 100.0) + EPSILON:
            gap = (unit_price - high_base) / high_base * 100.0
            return _hit("above_high", "Warning", "Notify Only", gap, high_base)

    return None  # OK


def _hit(rule_code, severity, recommended_action, gap_percent, reference_price):
    return {
        "rule_code": rule_code,
        "severity": severity,
        "recommended_action": recommended_action,
        "gap_percent": round(gap_percent, 2),
        "reference_price": reference_price,
    }


def _drop_gap(unit_price, reference):
    return (reference - unit_price) / reference * 100.0


def _f(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

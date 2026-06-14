"""Canonical Alert Center rule-code classification (Pre-E2E hardening
2026-06-14).

SINGLE SOURCE OF TRUTH for "is this rule_code an operational price alert, a
setup/configuration gap, or a system/integration failure?" Imported by
api_alerts and api_dashboard so the operational-vs-setup split can never
diverge across the alert list, KPIs, dimension/aging/trend aggregates and
exports.

Product decision (2026-06-14): the default operational Alert Center surfaces
ONLY operational price alerts. Setup / configuration gaps and system /
integration failures are NON-operational:

    * excluded from the DEFAULT list, KPIs, distributions, trend, aging and
      default exports;
    * still fully queryable - either by passing an explicit ``rule_code``
      filter (history / drill-down) or via the explicit Setup Issues view
      (``setup_only=1``).

Nothing is deleted or auto-closed; historical access is preserved.

The ``EC Alert.rule_code`` Select enum is the canonical inventory. The test
``test_rule_classification`` asserts every enum value is classified here, so a
newly-added rule_code can never silently slip into the operational default.
"""

# Operational price alerts - the real price-rule outputs a KAM / supervisor
# acts on day to day. These are the ONLY rules shown by default.
OPERATIONAL_RULES = frozenset({
    "below_min",
    "above_high",
    "severe_price_drop",
    "possible_missing_zero",
})

# Setup / configuration gaps - master-data work, NOT operational price
# incidents. ``missing_policy`` is retired (2026-06-14) but stays classified so
# historical records remain reachable; ``missing_brand_mapping`` is an unmapped
# shop->brand gap (brand-less by construction) and is this batch's decision.
SETUP_RULES = frozenset({
    "missing_policy",
    "missing_brand_mapping",
})

# System / integration failures - System Manager / Integration Health concern,
# surfaced on the Integration Health page (breaker / consecutive failures), not
# on the operational price dashboard.
SYSTEM_RULES = frozenset({
    "missing_integration_credential",
    "ingestion_api_failed",
    "stock_lock_api_failed",
})

# Everything that must NOT appear in the default OPERATIONAL views.
NON_OPERATIONAL_RULES = SETUP_RULES | SYSTEM_RULES

# Full canonical inventory (mirrors the EC Alert.rule_code Select enum). The
# inventory test asserts enum == ALL_RULES.
ALL_RULES = OPERATIONAL_RULES | NON_OPERATIONAL_RULES

# NOTE: services.case_todo also buckets rule_codes (INCIDENT / SETUP / SYSTEM),
# but for a DIFFERENT purpose - routing per-case KAM ToDos - so it intentionally
# classifies missing_brand_mapping as an INCIDENT (a KAM must map the shop). That
# is NOT a duplicate of THIS module, which decides dashboard/list VISIBILITY.
# Keep the two separate; do not merge (merging would change ToDo assignment).


def is_operational(code):
    return code in OPERATIONAL_RULES


def is_setup(code):
    return code in SETUP_RULES


def is_system(code):
    return code in SYSTEM_RULES


def classify(code):
    """Return 'operational' | 'setup' | 'system' | 'unknown'."""
    if code in OPERATIONAL_RULES:
        return "operational"
    if code in SETUP_RULES:
        return "setup"
    if code in SYSTEM_RULES:
        return "system"
    return "unknown"


def operational_rule_codes():
    return sorted(OPERATIONAL_RULES)


def setup_rule_codes():
    """Sorted list for the explicit Setup Issues view (rule_code IN ...)."""
    return sorted(SETUP_RULES)


def non_operational_rule_codes():
    """Sorted list for the default exclusion (rule_code NOT IN ...)."""
    return sorted(NON_OPERATIONAL_RULES)


def _truthy(v):
    return str(v).strip().lower() not in ("", "0", "false", "none", "no")


def rule_code_condition(f):
    """Canonical EC Alert ``rule_code`` filter triple for a dashboard / list
    filter dict ``f``. Precedence:

        1. explicit single ``rule_code``  -> exact match (history / drill-down)
        2. ``setup_only`` truthy          -> only setup/config rules
        3. default                        -> exclude all NON-operational rules

    Returns one 3-element frappe filter, e.g. ['rule_code','not in', [...]].
    Centralising this here means api_alerts and api_dashboard share ONE
    exclusion list (no duplication, no drift).
    """
    f = f or {}
    rc = f.get("rule_code")
    if rc:
        return ["rule_code", "=", rc]
    if _truthy(f.get("setup_only")):
        return ["rule_code", "in", setup_rule_codes()]
    return ["rule_code", "not in", non_operational_rule_codes()]

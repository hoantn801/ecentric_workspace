"""Phase G1 - Brand Onboarding Foundation & Integration Health (READ-ONLY).

Three whitelisted reads that power /alerts/integration-health:
    list_brand_readiness()      - one readiness row per brand the caller may see
    brand_readiness(brand)      - full detail + blockers + next action for one brand
    policy_coverage(brand)      - bounded 30-day SKU policy-coverage metric

Every endpoint gates on permissions.require_alert_center_access and scopes data
via get_allowed_brands. NO mutation, NO Omisell call, NO site_config write, NO
stock write - this module only reads existing records + cache + site_config.

SECRET SAFETY: BIS reads use an explicit field allowlist (_BIS_FIELDS) that
NEVER includes api_key / api_secret / token, so credentials cannot reach any
response even for a System Manager.
"""
import json

import frappe
from frappe.utils import add_days, get_datetime, now_datetime, nowdate

from ecentric_workspace.alerts import permissions as perms
from ecentric_workspace.alerts.services import brand_readiness as br

# secret-free BIS projection (api_key/api_secret/token deliberately absent)
_BIS_FIELDS = ["name", "enabled", "credential_status", "base_url",
               "last_sync_at", "consecutive_failures", "dry_run_stock_lock",
               "default_platform_scope"]

ARCHIVE_REVIEW_TRIGGER = 2000000  # == api_omisell.capacity_stats trigger
_RUNNING_KEY = "ec_alerts_pull_running_%s"   # == api_omisell._running_key
_LAST_RUN_KEY = "ec_alerts_pull_last_%s"     # == api_omisell._last_run_key


# --- config-tunable thresholds (defaults from brand_readiness) ---------------
def _thresholds():
    return {
        "stale_minutes": _conf_num("ec_alerts_health_stale_minutes", br.DEFAULT_STALE_MINUTES),
        "min_coverage": _conf_num("ec_alerts_health_min_coverage", br.DEFAULT_MIN_COVERAGE),
        "breaker_limit": br.DEFAULT_BREAKER_LIMIT,
    }


def _conf_num(key, default):
    try:
        v = frappe.conf.get(key)
    except Exception:
        return default
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _allowlist():
    """site_config ec_alerts_scheduled_pull_brands -> set of brand codes
    (fail-safe empty)."""
    try:
        v = frappe.conf.get("ec_alerts_scheduled_pull_brands")
    except Exception:
        return set()
    if not isinstance(v, (list, tuple)):
        return set()
    return set(str(x).strip() for x in v if str(x).strip())


def _cache_run(brand):
    cache = frappe.cache()
    running = cache.get_value(_RUNNING_KEY % brand)
    last = cache.get_value(_LAST_RUN_KEY % brand)
    if isinstance(last, bytes):
        last = last.decode()
    last_run = json.loads(last) if last else None
    return bool(running), (last_run or {}).get("state"), last_run


def _ba_rows(brands=None):
    """Active Brand Approver rows (optionally restricted to a code set)."""
    filters = {"status": ("in", ["Active", "Inactive"])}  # include inactive to flag it
    rows = frappe.get_all("Brand Approver", filters=filters,
                          fields=["name", "status", "kam_owner",
                                  "manager_email", "leader_email"])
    if brands is not None:
        rows = [r for r in rows if r["name"] in brands]
    return rows


def _bis_for(brand):
    name = frappe.db.get_value("EC Brand Integration Settings",
                               {"brand": brand, "integration_type": "Omisell"}, "name")
    if not name:
        return None
    vals = frappe.db.get_value("EC Brand Integration Settings", name,
                               _BIS_FIELDS, as_dict=True)
    return vals


def _counts(brand):
    return {
        "order_log": frappe.db.count("EC Marketplace Order Log", {"brand": brand}),
        "order_item": _item_count(brand),
        "alerts_open": frappe.db.count("EC Alert",
                                       {"brand": brand, "status": ("in", ["Open", "In Review"])}),
        "alerts_total": frappe.db.count("EC Alert", {"brand": brand}),
        "policies_active": frappe.db.count("EC Price Policy",
                                           {"brand": brand, "status": "Active"}),
    }


def _item_count(brand):
    # items are a child table -> count via the parent join (parameterized)
    row = frappe.db.sql(
        """SELECT COUNT(*) AS n FROM `tabEC Marketplace Order Item` oi
           JOIN `tabEC Marketplace Order Log` ol ON oi.parent = ol.name
           WHERE ol.brand = %s""", (brand,), as_dict=True)
    return row[0].n if row else 0


def _facts(ba, bis, allow, th, with_coverage=False):
    brand = ba["name"]
    running, last_state, _ = _cache_run(brand)
    age = None
    if bis and bis.get("last_sync_at"):
        age = (get_datetime(now_datetime()) - get_datetime(bis["last_sync_at"])).total_seconds() / 60.0
    facts = {
        "brand": brand,
        "ba_exists": True, "ba_status": ba.get("status"),
        "kam_owner": ba.get("kam_owner"),
        "manager_email": ba.get("manager_email"),
        "leader_email": ba.get("leader_email"),
        "bis_exists": bool(bis),
        "enabled": (bis or {}).get("enabled"),
        "credential_status": (bis or {}).get("credential_status"),
        "dry_run_stock_lock": (bis or {}).get("dry_run_stock_lock"),
        "consecutive_failures": (bis or {}).get("consecutive_failures"),
        "last_sync_at": (bis or {}).get("last_sync_at"),
        "sync_age_minutes": age,
        "running": running,
        "in_allowlist": brand in allow,
        "last_run_state": last_state,
        "stale_minutes": th["stale_minutes"],
        "min_coverage": th["min_coverage"],
        "breaker_limit": th["breaker_limit"],
    }
    if with_coverage and bis:
        cov = _coverage(brand, int(th.get("coverage_days", 30)))
        facts["coverage_pct"] = cov.get("pct")
    return facts


def _coverage(brand, days=30, sample=500):
    """Bounded: distinct seller_sku seen in the last `days` of order items vs
    those that have an Active EC Price Policy (seller_sku match). Cheap by
    construction - capped at `sample` distinct SKUs."""
    since = str(add_days(nowdate(), -int(days))) + " 00:00:00"
    seen = frappe.db.sql(
        """SELECT DISTINCT oi.seller_sku AS sku
           FROM `tabEC Marketplace Order Item` oi
           JOIN `tabEC Marketplace Order Log` ol ON oi.parent = ol.name
           WHERE ol.brand = %s AND ol.order_datetime >= %s
             AND oi.seller_sku IS NOT NULL AND oi.seller_sku != ''
           LIMIT %s""", (brand, since, int(sample)), as_dict=True)
    seen_skus = set(r.sku for r in seen)
    if not seen_skus:
        return {"distinct_skus": 0, "covered": 0, "pct": None,
                "sampled": True, "days": days}
    covered_rows = frappe.get_all(
        "EC Price Policy",
        filters={"brand": brand, "status": "Active",
                 "seller_sku": ("in", list(seen_skus))},
        fields=["seller_sku"], limit_page_length=0)
    covered = set(r.seller_sku for r in covered_rows) & seen_skus
    n = len(seen_skus)
    return {"distinct_skus": n, "covered": len(covered),
            "pct": round(100.0 * len(covered) / n, 1),
            "sampled": n >= sample, "days": days}


def _capacity():
    """Global Log+Item row counts vs the 2M archive-review trigger (SM only)."""
    log = frappe.db.count("EC Marketplace Order Log")
    item = frappe.db.count("EC Marketplace Order Item")
    lpi = log + item
    return {"order_log": log, "order_item": item, "log_plus_item": lpi,
            "archive_review_trigger": ARCHIVE_REVIEW_TRIGGER,
            "archive_review_due": lpi >= ARCHIVE_REVIEW_TRIGGER}


# --- endpoints ---------------------------------------------------------------

@frappe.whitelist()
def list_brand_readiness():
    """One readiness row per brand the caller may see. SM sees all Brand
    Approver brands; scoped users see their brands only. Capacity block is
    SM-only (global counts)."""
    allowed = perms.require_alert_center_access()
    is_sm = (allowed == perms.ALL_BRANDS)
    th = _thresholds()
    allow = _allowlist()

    codes = None if is_sm else set(allowed.keys())
    rows = []
    for ba in _ba_rows(codes):
        bis = _bis_for(ba["name"])
        facts = _facts(ba, bis, allow, th)
        verdict = br.derive(facts)
        counts = _counts(ba["name"])
        rows.append({
            "brand": ba["name"],
            "status": verdict["status"],
            "running": verdict["running"],
            "action": verdict["action"],
            "blockers": verdict["blockers"],
            "kam_owner": ba.get("kam_owner"),
            "manager_email": ba.get("manager_email"),
            "leader_email": ba.get("leader_email"),
            "ba_status": ba.get("status"),
            "bis_exists": bool(bis),
            "credential_status": (bis or {}).get("credential_status"),
            "enabled": (bis or {}).get("enabled"),
            "dry_run_stock_lock": (bis or {}).get("dry_run_stock_lock"),
            "last_sync_at": str((bis or {}).get("last_sync_at") or "") or None,
            "consecutive_failures": int((bis or {}).get("consecutive_failures") or 0),
            "in_allowlist": ba["name"] in allow,
            "last_run_state": facts["last_run_state"],
            "counts": counts,
        })
    rows.sort(key=lambda r: (_STATUS_ORDER.get(r["status"], 9), r["brand"]))
    out = {"brands": rows, "thresholds": th, "is_supervisor": is_sm}
    if is_sm:
        out["capacity"] = _capacity()
    return out


_STATUS_ORDER = {br.BLOCKED: 0, br.WARNING: 1, br.MANUAL_PULL: 2,
                 br.RUNNING: 3, br.READY: 4, br.SCHEDULER_ENABLED: 5}


@frappe.whitelist()
def brand_readiness(brand):
    """Full readiness detail for one brand (drawer feed)."""
    perms.require_brand_access(frappe.session.user, brand)
    th = _thresholds()
    th["coverage_days"] = 30
    allow = _allowlist()
    ba_rows = _ba_rows({brand})
    if not ba_rows:
        # Brand Approver missing entirely -> synthesize a Blocked verdict
        verdict = br.derive({"brand": brand, "ba_exists": False})
        return {"brand": brand, "status": verdict["status"],
                "blockers": verdict["blockers"], "action": verdict["action"],
                "running": False, "bis_exists": False, "counts": {}, "coverage": {}}
    ba = ba_rows[0]
    bis = _bis_for(brand)
    facts = _facts(ba, bis, allow, th, with_coverage=True)
    verdict = br.derive(facts)
    running, last_state, last_run = _cache_run(brand)
    return {
        "brand": brand,
        "status": verdict["status"], "running": verdict["running"],
        "blockers": verdict["blockers"], "action": verdict["action"],
        "brand_approver": {"status": ba.get("status"),
                           "kam_owner": ba.get("kam_owner"),
                           "manager_email": ba.get("manager_email"),
                           "leader_email": ba.get("leader_email")},
        "bis": bis,  # secret-free projection only
        "bis_exists": bool(bis),
        "in_allowlist": brand in allow,
        "last_run_state": last_state,
        "last_run": last_run,
        "counts": _counts(brand),
        "coverage": _coverage(brand, int(th.get("coverage_days", 30))) if bis else {},
        "thresholds": th,
    }


@frappe.whitelist()
def policy_coverage(brand, days=30, sample=500):
    """Bounded SKU policy-coverage metric for one brand (split out as the
    heaviest query)."""
    perms.require_brand_access(frappe.session.user, brand)
    return _coverage(brand, int(days or 30), int(sample or 500))

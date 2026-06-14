"""Phase F - Dashboard v2 aggregations. All scoped server-side; default date
range = LAST 14 DAYS (approved requirement #4); served by D.1 indexes."""
import json

import frappe
from frappe.utils import add_days, nowdate

from ecentric_workspace.alerts import permissions as perms
from ecentric_workspace.alerts.services import case_lifecycle as cl
from ecentric_workspace.alerts.services import rule_classification as rclass

DEFAULT_DAYS = 14
# Step 1 (2026-06-13): canonical completed = Closed; legacy Resolved counted
# during the transitional release. Single source of truth.
COMPLETED_STATUSES = list(cl.COMPLETED_STATUSES)
ACTIVE_STATUSES = list(cl.ACTIVE_STATUSES)
DIMENSIONS = {"brand": "brand", "platform": "platform", "shop": "shop",
              "rule_code": "rule_code"}


def _flt(f=None, days=None, rule_override=None):
    """Build the scoped EC Alert filter list for every dashboard aggregate.

    rule_override: pass an explicit ['rule_code', op, value] triple to replace
    the canonical operational/setup rule scoping (used by the Setup Issues KPI).
    When None, the rule_code condition comes from the SINGLE canonical helper
    rule_classification.rule_code_condition (operational default excludes setup
    + system rules; explicit rule_code or setup_only=1 opt back in)."""
    allowed = perms.require_alert_center_access()
    f = json.loads(f) if isinstance(f, str) else (f or {})
    flt = []
    for k in ("platform", "shop", "severity", "status", "owner_user"):
        if f.get(k):
            flt.append([k, "=", f[k]])
    # 2026-06-14 (Pre-E2E): operational dashboards (KPI, by_dimension, top_skus,
    # aging, trend, hourly) exclude NON-operational rules (setup gaps such as
    # missing_brand_mapping / missing_policy + system failures) by default.
    # One canonical exclusion list, shared with api_alerts.
    flt.append(rule_override if rule_override is not None
               else rclass.rule_code_condition(f))
    if f.get("seller_sku"):
        flt.append(["seller_sku", "like", "%%%s%%" % f["seller_sku"]])
    frm = f.get("from_date") or add_days(nowdate(), -(days or DEFAULT_DAYS))
    to = f.get("to_date")
    flt.append(["detected_at", ">=", str(frm) + " 00:00:00" if len(str(frm)) == 10 else frm])
    if to:
        flt.append(["detected_at", "<=", str(to) + " 23:59:59" if len(str(to)) == 10 else to])
    if allowed != perms.ALL_BRANDS:
        scope = [b for b in allowed if not f.get("brand") or b == f["brand"]]
        if not scope:
            return None
        flt.append(["brand", "in", scope])
    elif f.get("brand"):
        flt.append(["brand", "=", f["brand"]])
    return flt


# --- safe aggregate SQL (Frappe bans SQL-function strings in get_all fields;
# caught by our own TestNoSqlFunctionStrings lint) -------------------------
_OPS = {"=": "= %s", "in": None, "like": "LIKE %s", ">=": ">= %s", "<=": "<= %s"}
_COLS = {"brand", "platform", "shop", "rule_code", "severity", "status",
         "owner_user", "seller_sku", "detected_at", "resolved_at"}


def _where(flt):
    """Internal filter triples -> parameterized WHERE. Column names come from
    our own whitelists only (never user input)."""
    conds, params = [], []
    for field, op, value in flt:
        assert field in _COLS, field
        if op == "in":
            conds.append("`%s` IN (%s)" % (field, ", ".join(["%s"] * len(value))))
            params += list(value)
        elif op == "not in":
            conds.append("`%s` NOT IN (%s)" % (field, ", ".join(["%s"] * len(value))))
            params += list(value)
        elif op == "is" and value == "set":
            conds.append("`%s` IS NOT NULL AND `%s` != ''" % (field, field))
        else:
            conds.append("`%s` %s" % (field, _OPS[op]))
            params.append(value)
    return (" AND ".join(conds) or "1=1"), params


def _group_count(flt, field, limit=12):
    assert field in _COLS
    where, params = _where(flt)
    rows = frappe.db.sql(
        """SELECT `%s` AS k, COUNT(*) AS n FROM `tabEC Alert`
           WHERE %s GROUP BY `%s` ORDER BY n DESC LIMIT %d"""
        % (field, where, field, int(limit)), params, as_dict=True)
    return [{"key": r.k or "(none)", "n": r.n} for r in rows]


@frappe.whitelist()
def kpis(filters=None):
    flt = _flt(filters)
    if flt is None:
        return {}
    def c(extra):
        return frappe.db.count("EC Alert", filters=flt + extra)
    # Setup Issues use a dedicated filter that opts INTO setup/config rules
    # (the operational `flt` excludes them). Same brand scope + date window, so
    # KAM (brand-scoped) sees 0 brand-less missing_brand_mapping; supervisors
    # see them. Falls back to 0 if scope intersection is empty.
    setup_flt = _flt(filters, rule_override=["rule_code", "in",
                                             rclass.setup_rule_codes()])
    def cs(extra):
        return 0 if setup_flt is None else frappe.db.count(
            "EC Alert", filters=setup_flt + extra)
    open_f = [["status", "in", ACTIVE_STATUSES]]
    setup_open = cs(open_f)
    return {
        # Operational KPIs - exclude setup + system rules by construction.
        "open": c(open_f),
        "critical": c(open_f + [["severity", "=", "Critical"]]),
        "warning": c(open_f + [["severity", "=", "Warning"]]),
        # 2026-06-14 (Pre-E2E): replaces the stale "Thieu policy" card. Counts
        # OPEN setup/configuration gaps (missing_brand_mapping + retired
        # missing_policy) within scope - never mixed into the operational KPIs.
        "setup_issues": setup_open,
        # Legacy FE key kept as an alias during the frontend transition (old
        # builds read c.missing_policy). Same value as setup_issues; no longer
        # labelled "missing policy" in the UI.
        "missing_policy": setup_open,
        # API key `resolved` kept for frontend compatibility (the dashboard
        # card reads c.resolved). Value = COMPLETED = Closed + legacy Resolved.
        # `closed` is the forward-compat alias; both carry the same count.
        # Cancelled is NOT counted here (excluded from the handled KPI).
        "resolved": c([["status", "in", COMPLETED_STATUSES]]),
        "closed": c([["status", "in", COMPLETED_STATUSES]]),
        "ignored": c([["status", "=", "Ignored"]]),
        "lock_pending_review": frappe.db.count("EC Alert Action", {
            "action_type": "Stock Safety Lock", "review_status": "Pending Review"}),
    }


@frappe.whitelist()
def by_dimension(dim, filters=None):
    field = DIMENSIONS.get(dim)
    if not field:
        frappe.throw("invalid dimension")
    flt = _flt(filters)
    return {"rows": [] if flt is None else _group_count(flt, field)}


@frappe.whitelist()
def top_skus(filters=None, limit=10):
    flt = _flt(filters)
    if flt is None:
        return {"rows": []}
    where, params = _where(flt + [["seller_sku", "is", "set"]])
    rows = frappe.db.sql(
        """SELECT seller_sku, brand, COUNT(*) AS n, MAX(detected_at) AS latest
           FROM `tabEC Alert` WHERE %s GROUP BY seller_sku, brand
           ORDER BY n DESC LIMIT %d""" % (where, min(int(limit or 10), 25)),
        params, as_dict=True)
    return {"rows": rows}


@frappe.whitelist()
def aging(filters=None):
    """Unresolved (Open/In Review) age buckets."""
    flt = _flt(filters, days=365)  # aging looks beyond the 14d default window
    if flt is None:
        return {}
    flt = [x for x in flt if x[0] != "detected_at"]  # aging = all unresolved
    flt += [["status", "in", ACTIVE_STATUSES]]
    buckets = {"lt_4h": 0, "h4_24": 0, "d1_3": 0, "gt_3d": 0}
    rows = frappe.get_all("EC Alert", filters=flt, fields=["detected_at"],
                          limit_page_length=0)
    from frappe.utils import now_datetime, get_datetime
    now = now_datetime()
    for r in rows:
        if not r.detected_at:
            continue
        h = (now - get_datetime(r.detected_at)).total_seconds() / 3600.0
        buckets["lt_4h" if h < 4 else "h4_24" if h < 24 else "d1_3" if h < 72 else "gt_3d"] += 1
    return buckets


@frappe.whitelist()
def trend(filters=None, days=DEFAULT_DAYS):
    """Daily Closed vs Ignored vs New counts for the last N days. Output key
    `resolved` kept for frontend compatibility = COMPLETED (Closed + legacy
    Resolved during transition); Cancelled excluded."""
    days = min(int(days or DEFAULT_DAYS), 31)
    flt = _flt(filters, days=days)
    if flt is None:
        return {"rows": []}
    base = [x for x in flt if x[0] != "detected_at"]
    out = []
    for off in range(days - 1, -1, -1):
        day = add_days(nowdate(), -off)
        d0, d1 = str(day) + " 00:00:00", str(day) + " 23:59:59"
        out.append({"day": str(day),
                    "new": frappe.db.count("EC Alert", filters=base +
                                           [["detected_at", ">=", d0], ["detected_at", "<=", d1]]),
                    "resolved": frappe.db.count("EC Alert", filters=base +
                                                [["status", "in", COMPLETED_STATUSES],
                                                 ["resolved_at", ">=", d0], ["resolved_at", "<=", d1]]),
                    "ignored": frappe.db.count("EC Alert", filters=base +
                                               [["status", "=", "Ignored"],
                                                ["resolved_at", ">=", d0], ["resolved_at", "<=", d1]])})
    return {"rows": out}


@frappe.whitelist()
def hourly_trend(filters=None):
    """Alerts detected per hour-of-day (0-23): total + critical. Honors the
    same dashboard filters/scope. Read-only, parameterized SQL."""
    flt = _flt(filters)
    empty = [{"hour": h, "total": 0, "critical": 0} for h in range(24)]
    if flt is None:
        return {"rows": empty}
    where, params = _where(flt)
    rows = frappe.db.sql(
        """SELECT HOUR(detected_at) AS h, COUNT(*) AS total,
                  SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) AS critical
           FROM `tabEC Alert` WHERE %s AND detected_at IS NOT NULL
           GROUP BY HOUR(detected_at)""" % where, params, as_dict=True)
    by = {int(r.h): r for r in rows if r.h is not None}
    return {"rows": [{"hour": h,
                      "total": int(by[h].total) if h in by else 0,
                      "critical": int(by[h].critical or 0) if h in by else 0}
                     for h in range(24)]}

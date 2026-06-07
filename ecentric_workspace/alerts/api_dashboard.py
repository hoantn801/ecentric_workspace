"""Phase F - Dashboard v2 aggregations. All scoped server-side; default date
range = LAST 14 DAYS (approved requirement #4); served by D.1 indexes."""
import json

import frappe
from frappe.utils import add_days, nowdate

from ecentric_workspace.alerts import permissions as perms

DEFAULT_DAYS = 14
DIMENSIONS = {"brand": "brand", "platform": "platform", "shop": "shop",
              "rule_code": "rule_code"}


def _flt(f=None, days=None):
    allowed = perms.require_alert_center_access()
    f = json.loads(f) if isinstance(f, str) else (f or {})
    flt = []
    for k in ("platform", "shop", "severity", "status", "owner_user", "rule_code"):
        if f.get(k):
            flt.append([k, "=", f[k]])
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
    open_f = [["status", "in", ["Open", "In Review"]]]
    return {
        "open": c(open_f),
        "critical": c(open_f + [["severity", "=", "Critical"]]),
        "warning": c(open_f + [["severity", "=", "Warning"]]),
        "missing_policy": c(open_f + [["rule_code", "in",
                                       ["missing_policy", "missing_brand_mapping"]]]),
        "resolved": c([["status", "=", "Resolved"]]),
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
    flt += [["status", "in", ["Open", "In Review"]]]
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
    """Daily Resolved vs Ignored vs New counts for the last N days."""
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
                                                [["status", "=", "Resolved"],
                                                 ["resolved_at", ">=", d0], ["resolved_at", "<=", d1]]),
                    "ignored": frappe.db.count("EC Alert", filters=base +
                                               [["status", "=", "Ignored"],
                                                ["resolved_at", ">=", d0], ["resolved_at", "<=", d1]])})
    return {"rows": out}

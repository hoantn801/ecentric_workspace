"""Case-grouping repair (2026-06-11) - reassign occurrences to correct cases.

Bug: Case grouping keyed on brand+sku+rule only, so occurrences from a
different platform/shop attached to the same open case (Lazada P02056
evidence under Shopee case EC-AL-000708). The engine fix (alert_engine.
_find_or_create_case + dedupe_keys.case_key) separates NEW cases by
brand+platform+shop+sku+rule; this module repairs EXISTING mixed cases.

What it does, per mixed case (an Open/In Review price-rule EC Alert whose
occurrences span more than one platform+shop, or differ from the case's own
platform/shop):
  1. keeps the occurrence group matching the case's platform+shop on the case;
  2. for every other group: finds an open case with the correct scope or
     creates one (key = dedupe_keys.case_key with the group's first
     order/line), then repoints those occurrences' `case` field;
  3. recalculates rollups on every touched case FROM its occurrences:
     occurrence_count, first_seen_at, last_seen_at, worst_gap_percent,
     effective_check_price / actual_price / gap_percent (latest occurrence);
  4. leaves a Comment on every touched case (audit trail).

Safety: SM-only POST; dry_run=1 DEFAULT (returns the full plan, writes
nothing); never deletes anything; never touches status; missing_policy /
missing_brand_mapping cases are out of scope (no occurrences). No Omisell
call, no stock write, no scheduler/hooks change. Code-only, no migrate.
"""
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.alerts.services import brand_resolver, dedupe_keys

PRICE_RULES = ("below_min", "above_high", "severe_price_drop",
               "possible_missing_zero")
ACTIVE = ("Open", "In Review")

OCC_FIELDS = ["name", "platform", "shop", "seller_sku", "item", "rule_code",
              "external_order_id", "external_line_id", "detected_at",
              "gap_percent", "effective_check_price", "price_components_used",
              "min_price_at_check", "baseline_price_at_check", "product_name"]


def _occ_of(case_name):
    return frappe.get_all("EC Alert Occurrence", filters={"case": case_name},
                          fields=OCC_FIELDS, order_by="detected_at asc",
                          limit_page_length=0)


def _group_key(o):
    return (o.platform or "", o.shop or "")


def _recalc(case_name):
    """Rebuild Case rollups from its occurrences (source of truth)."""
    occ = _occ_of(case_name)
    case = frappe.get_doc("EC Alert", case_name)
    case.occurrence_count = len(occ)
    if occ:
        case.first_seen_at = occ[0].detected_at
        case.last_seen_at = occ[-1].detected_at
        case.worst_gap_percent = max(float(o.gap_percent or 0) for o in occ)
        latest = occ[-1]
        case.effective_check_price = latest.effective_check_price
        case.actual_price = latest.effective_check_price
        case.gap_percent = latest.gap_percent
        if latest.price_components_used:
            case.price_components_used = latest.price_components_used
    case.save(ignore_permissions=True)
    return case.occurrence_count


def _find_or_create_target(src_case, group, occ_rows):
    """Open case with the correct scope, or a new one cloned from the source
    case + the group's first occurrence. Returns (name, created)."""
    platform, shop = group
    existing = frappe.db.get_value("EC Alert", {
        "brand": src_case.brand, "platform": platform, "shop": shop,
        "seller_sku": src_case.seller_sku, "rule_code": src_case.rule_code,
        "status": ["in", list(ACTIVE)]}, "name")
    if existing:
        return existing, False
    first = occ_rows[0]
    key = dedupe_keys.case_key(src_case.brand, platform, shop,
                               src_case.seller_sku, src_case.rule_code,
                               first.external_order_id, first.external_line_id)
    doc = frappe.get_doc({
        "doctype": "EC Alert",
        "alert_type": src_case.alert_type,
        "rule_code": src_case.rule_code,
        "severity": src_case.severity,
        "status": "Open",
        "title": (src_case.title or "")[:140],
        "message": ("Case for brand %s / %s / %s / SKU %s / rule %s. Split "
                    "from %s by repair_case_grouping (case-grouping fix "
                    "2026-06-11)." % (src_case.brand, platform, shop,
                                      src_case.seller_sku, src_case.rule_code,
                                      src_case.name)),
        "brand": src_case.brand,
        "platform": platform,
        "shop": shop,
        "item": first.item or src_case.item,
        "seller_sku": src_case.seller_sku,
        "owner_user": brand_resolver.resolve_owner(shop, src_case.brand),
        "source_system": src_case.source_system or "Omisell",
        "reference_doctype": src_case.reference_doctype,
        "reference_name": src_case.reference_name,
        "min_price": first.min_price_at_check if first.min_price_at_check
                     is not None else src_case.min_price,
        "baseline_price": first.baseline_price_at_check
                          if first.baseline_price_at_check is not None
                          else src_case.baseline_price,
        "recommended_action": src_case.recommended_action,
        "occurrence_count": 0,
        "dedupe_key": key,
        "detected_at": now_datetime(),
    })
    doc.insert(ignore_permissions=True)
    return doc.name, True


@frappe.whitelist(methods=["POST"])
def repair_case_grouping(brand=None, dry_run=1):
    """Scan active price-rule cases for mixed platform/shop occurrence groups
    and (unless dry_run) split them into correctly-scoped cases + recalc
    rollups. Always returns the full plan/result for audit."""
    frappe.only_for("System Manager")
    dry = int(dry_run or 0)
    flt = {"rule_code": ["in", list(PRICE_RULES)],
           "status": ["in", list(ACTIVE)],
           "occurrence_count": [">", 0]}
    if brand:
        flt["brand"] = brand
    cases = frappe.get_all("EC Alert", filters=flt,
                           fields=["name"], limit_page_length=0)
    out = {"dry_run": dry, "brand": brand, "scanned": len(cases),
           "mixed_cases": [], "actions": [], "errors": []}
    for c in cases:
        try:
            src = frappe.get_doc("EC Alert", c.name)
            occ = _occ_of(src.name)
            if not occ:
                continue
            groups = {}
            for o in occ:
                groups.setdefault(_group_key(o), []).append(o)
            own = (src.platform or "", src.shop or "")
            stray = {g: rows for g, rows in groups.items() if g != own}
            if not stray:
                continue
            plan = {"case": src.name, "case_scope": list(own),
                    "groups": {("%s|%s" % g): len(rows)
                               for g, rows in groups.items()}}
            out["mixed_cases"].append(plan)
            if dry:
                continue
            moved_total = 0
            for g, rows in stray.items():
                target, created = _find_or_create_target(src, g, rows)
                for o in rows:
                    frappe.db.set_value("EC Alert Occurrence", o.name,
                                        "case", target)
                moved_total += len(rows)
                n_target = _recalc(target)
                frappe.get_doc("EC Alert", target).add_comment(
                    "Comment", "repair_case_grouping: received %d occurrence(s) "
                    "from %s (scope %s|%s). occurrence_count=%d"
                    % (len(rows), src.name, g[0], g[1], n_target))
                out["actions"].append({
                    "from_case": src.name, "to_case": target,
                    "to_scope": list(g), "moved": len(rows),
                    "target_created": created})
            n_src = _recalc(src.name)
            frappe.get_doc("EC Alert", src.name).add_comment(
                "Comment", "repair_case_grouping: moved out %d stray "
                "occurrence(s) to platform/shop-scoped case(s). "
                "occurrence_count=%d%s" % (
                    moved_total, n_src,
                    " - NO occurrences left, review/resolve manually"
                    if n_src == 0 else ""))
            if n_src == 0:
                out.setdefault("empty_after_repair", []).append(src.name)
        except Exception as e:
            out["errors"].append({"case": c.name, "error": str(e)[:200]})
            frappe.log_error(frappe.get_traceback(),
                             "alerts.repair_case_grouping %s" % c.name)
    out["mixed_total"] = len(out["mixed_cases"])
    frappe.logger("alerts").info({"repair_case_grouping": json.dumps(
        {k: out[k] for k in ("dry_run", "brand", "scanned", "mixed_total")})})
    return out

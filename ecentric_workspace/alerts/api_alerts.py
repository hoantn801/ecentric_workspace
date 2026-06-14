"""Alert Center UI endpoints - alerts list / KPI cards / status handling.
Phase E. Every endpoint: (1) require_alert_center_access first line,
(2) brand scope filtered SERVER-SIDE from Brand Approver (decision D2),
(3) writes POST-only, (4) Resolve/Ignore note required server-side.
NOTE: brand-less alerts (missing_brand_mapping) are visible to supervisors
only - KAM scope is brand-keyed by definition.
"""
import json

import frappe
from frappe import _
from frappe.utils import cint, nowdate

from ecentric_workspace.alerts import permissions as perms
from ecentric_workspace.alerts.services import case_lifecycle as cl
from ecentric_workspace.alerts.services import rule_classification as rclass

# Step 1 (2026-06-13): canonical completed status is Closed. KAM/Manager may
# move a case to In Review / Closed / Ignored only (Cancelled is supervisor-
# only via cancel_case). Resolved is NEVER written.
HANDLE_STATUSES = ("In Review", "Closed", "Ignored")
NOTE_REQUIRED = ("Closed", "Ignored")
MAX_PAGE = 100

LIST_FIELDS = [
    "name", "alert_type", "rule_code", "severity", "status", "title",
    "brand", "platform", "shop", "item", "seller_sku", "owner_user",
    "actual_price", "min_price", "baseline_price", "gap_percent",
    "recommended_action", "detected_at", "reference_doctype",
    "reference_name", "resolved_by", "resolved_at",
    # G1.1 evidence rollup
    "occurrence_count", "effective_check_price", "price_components_used",
    "first_seen_at", "last_seen_at", "worst_gap_percent",
]

# G1.1 per-order-line evidence projection (EC Alert Occurrence) - the price
# breakdown columns the drawer renders (RSP - components = effective).
OCC_FIELDS = [
    "name", "external_order_id", "order_datetime", "order_status",
    "seller_sku", "product_name", "rsp_price", "seller_discount_amount",
    "seller_voucher_amount", "platform_discount_amount", "platform_voucher_amount",
    "customer_paid_price", "effective_check_price", "price_components_used",
    "min_price_at_check", "baseline_price_at_check", "gap_percent",
    "rule_code", "severity", "detected_at",
]


def _parse(filters):
    if isinstance(filters, str):
        filters = json.loads(filters or "{}")
    return filters or {}


def _scoped_filters(f, allowed):
    """Build frappe filter list; returns None when scope intersection is empty."""
    flt = []
    for k in ("severity", "alert_type", "platform", "owner_user"):
        if f.get(k):
            flt.append([k, "=", f[k]])
    # status accepts a single value (the filter dropdown) OR a list (a KPI card
    # group such as Open+In Review / Closed+Resolved). Additive - the single
    # form is unchanged; the list form adds an IN without removing capability.
    st = f.get("status")
    if st:
        if isinstance(st, str):
            try:
                parsed = json.loads(st)
                st = parsed if isinstance(parsed, list) else st
            except (ValueError, TypeError):
                pass
        if isinstance(st, (list, tuple)):
            vals = [s for s in st if s]
            if vals:
                flt.append(["status", "in", list(vals)])
        else:
            flt.append(["status", "=", st])
    # 2026-06-14 (Pre-E2E): the default operational Alerts list excludes
    # NON-operational rules (setup gaps such as missing_brand_mapping /
    # missing_policy + system failures). One canonical condition shared with
    # api_dashboard: explicit rule_code='...' or setup_only=1 opts back in, so
    # history and the Setup Issues view stay fully queryable.
    flt.append(rclass.rule_code_condition(f))
    if f.get("seller_sku"):
        # UX polish 2026-06-10: EXACT match by default so P02056 never mixes
        # with P02056X2; a '*' in the query opts into wildcard (like) matching.
        # (Before this, the seller_sku filter key was silently ignored.)
        v = str(f["seller_sku"]).strip()
        if v:
            if "*" in v:
                flt.append(["seller_sku", "like", v.replace("*", "%")])
            else:
                flt.append(["seller_sku", "=", v])
    if f.get("from_date"):
        flt.append(["detected_at", ">=", f["from_date"]])
    if f.get("to_date"):
        flt.append(["detected_at", "<=", str(f["to_date"]) + " 23:59:59"
                    if len(str(f["to_date"])) == 10 else f["to_date"]])
    if allowed == perms.ALL_BRANDS:
        if f.get("brand"):
            flt.append(["brand", "=", f["brand"]])
    else:
        scope = list(allowed)
        if f.get("brand"):
            scope = [b for b in scope if b == f.get("brand")]
        if not scope:
            return None
        flt.append(["brand", "in", scope])
    return flt


@frappe.whitelist()
def list_alerts(filters=None, start=0, page_len=50):
    allowed = perms.require_alert_center_access()
    flt = _scoped_filters(_parse(filters), allowed)
    if flt is None:
        return {"rows": [], "total": 0}
    rows = frappe.get_all(
        "EC Alert", filters=flt, fields=LIST_FIELDS,
        order_by="detected_at desc, creation desc",
        start=cint(start), page_length=min(cint(page_len) or 50, MAX_PAGE))
    # Frappe-safe count (no SQL function strings - hotfix 2026-06-09);
    # frappe.db.count accepts the same 3-element list filters as get_all.
    total = frappe.db.count("EC Alert", filters=flt)
    # latest lock-action status per alert (Action Status column)
    names = [r.name for r in rows]
    if names:
        acts = frappe.get_all(
            "EC Alert Action", filters={"alert": ("in", names)},
            fields=["alert", "name", "status", "action_type"],
            order_by="creation desc")
        seen = {}
        for a in acts:
            if a.alert not in seen:
                seen[a.alert] = a
        for r in rows:
            a = seen.get(r.name)
            r["action_status"] = a.status if a else None
            r["action_name"] = a.name if a else None
    return {"rows": rows, "total": total}


@frappe.whitelist()
def get_cards():
    """COUNT(*)-based KPIs (Phase D.1): constant memory at any table size,
    served by the (brand, status, detected_at) composite index."""
    allowed = perms.require_alert_center_access()
    scope = None if allowed == perms.ALL_BRANDS else list(allowed)

    def count(extra):
        f = dict(extra)
        if scope is not None:
            f["brand"] = ("in", scope)
        # 2026-06-14 (Pre-E2E): operational KPIs exclude NON-operational rules
        # (setup gaps + system failures) unless the caller scopes rule_code
        # explicitly. Canonical exclusion list (shared with api_dashboard).
        f.setdefault("rule_code", ("not in", rclass.non_operational_rule_codes()))
        return frappe.db.count("EC Alert", f)

    def setup_count(extra):
        f = dict(extra)
        if scope is not None:
            f["brand"] = ("in", scope)
        f["rule_code"] = ("in", rclass.setup_rule_codes())
        return frappe.db.count("EC Alert", f)

    open_states = {"status": ("in", list(cl.ACTIVE_STATUSES))}
    af = {"action_type": "Stock Safety Lock", "status": ("in", ["Pending", "Dry Run"])}
    if scope is not None:
        af["brand"] = ("in", scope)
    # "Closed today": canonical Closed + legacy Resolved during transition.
    closed_states = list(("Closed",) + cl.LEGACY_TERMINAL)
    setup_open = setup_count(open_states)
    return {
        "open": count(open_states),
        "critical": count(dict(open_states, severity="Critical")),
        "warning": count(dict(open_states, severity="Warning")),
        # 2026-06-14 (Pre-E2E): setup/configuration gaps, separated from the
        # operational KPIs. Legacy key `missing_policy` kept as an alias.
        "setup_issues": setup_open,
        "missing_policy": setup_open,
        "lock_pending": frappe.db.count("EC Alert Action", af),
        "closed_today": count({"status": ("in", closed_states),
                               "resolved_at": (">=", nowdate() + " 00:00:00")}),
    }


@frappe.whitelist(methods=["POST"])
def set_status(alert, new_status, note=None):
    perms.require_alert_center_access()
    if new_status not in HANDLE_STATUSES:
        frappe.throw(_("Invalid status {0}.").format(new_status))
    doc = frappe.get_doc("EC Alert", alert)
    user = frappe.session.user
    if doc.brand:
        if not perms.can_handle_alert(user, doc.brand):
            frappe.throw(_("You cannot handle alerts of brand {0}.").format(doc.brand),
                         frappe.PermissionError)
    elif not perms.is_global_supervisor(user):
        # brand-less alert (unmapped shop) -> supervisors only
        frappe.throw(_("Only supervisors can handle unmapped-brand alerts."),
                     frappe.PermissionError)
    # TRANSITION GUARD (Step 1): no reopening a terminal case; only
    # Open->In Review/Closed/Ignored and In Review->Closed/Ignored allowed.
    if not cl.can_transition(doc.status, new_status):
        frappe.throw(_("Cannot change case {0} from {1} to {2}.").format(
            doc.name, doc.status, new_status), frappe.ValidationError)
    if new_status in NOTE_REQUIRED and not (note and str(note).strip()):
        frappe.throw(_("A note is required to mark an alert {0}.").format(new_status))
    doc.status = new_status
    if note and str(note).strip():
        doc.resolution_note = str(note).strip()
    doc.save(ignore_permissions=True)  # controller stamps resolved_by/resolved_at
    return {"name": doc.name, "status": doc.status,
            "resolved_by": doc.resolved_by, "resolved_at": doc.resolved_at}


@frappe.whitelist(methods=["POST"])
def bulk_set_status(names, new_status, note=None):
    """G1.1: apply a status to multiple Cases at once. Per-row brand scope is
    enforced (same rule as set_status); a denied/failed row never aborts the
    batch. Returns {ok, denied, failed} name lists."""
    perms.require_alert_center_access()
    if new_status not in HANDLE_STATUSES:
        frappe.throw(_("Invalid status {0}.").format(new_status))
    if isinstance(names, str):
        names = json.loads(names or "[]")
    if new_status in NOTE_REQUIRED and not (note and str(note).strip()):
        frappe.throw(_("A note is required to mark alerts {0}.").format(new_status))
    note = str(note).strip() if (note and str(note).strip()) else None
    user = frappe.session.user
    res = {"ok": [], "denied": [], "failed": []}
    for nm in (names or []):
        try:
            doc = frappe.get_doc("EC Alert", nm)
            if doc.brand:
                if not perms.can_handle_alert(user, doc.brand):
                    res["denied"].append(nm)
                    continue
            elif not perms.is_global_supervisor(user):
                res["denied"].append(nm)
                continue
            # no-reopen / valid-transition guard, per row (Step 1)
            if not cl.can_transition(doc.status, new_status):
                res["failed"].append(nm)
                continue
            doc.status = new_status
            if note:
                doc.resolution_note = note
            doc.save(ignore_permissions=True)
            res["ok"].append(nm)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "alerts.bulk_set_status %s" % nm)
            res["failed"].append(nm)
    return res


@frappe.whitelist(methods=["POST"])
def cancel_case(alert, reason=None):
    """Cancel a case (terminal, KPI-excluded) - SUPERVISOR/ADMIN ONLY
    (decision D6). Reason required. Not exposed to KAM/Manager UI. Only an
    active case may be cancelled; a cancelled case is frozen like any other
    terminal state and never reopens."""
    perms.require_alert_center_access()
    if not perms.can_cancel_case(frappe.session.user):
        frappe.throw(_("Only System Manager can cancel a case."),
                     frappe.PermissionError)
    if not (reason and str(reason).strip()):
        frappe.throw(_("A reason is required to cancel a case."))
    doc = frappe.get_doc("EC Alert", alert)
    if not cl.can_cancel(doc.status):
        frappe.throw(_("Case {0} is {1} and cannot be cancelled.").format(
            doc.name, doc.status), frappe.ValidationError)
    doc.status = "Cancelled"
    doc.resolution_note = str(reason).strip()
    doc.save(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status,
            "resolved_by": doc.resolved_by, "resolved_at": doc.resolved_at}


@frappe.whitelist()
def alert_occurrences(alert, start=0, page_len=50):
    """G1.1: per-order-line evidence rows for one Case (brand-scoped)."""
    perms.require_alert_center_access()
    row = frappe.db.get_value("EC Alert", alert, ["brand"], as_dict=True)
    if not row:
        frappe.throw(_("Alert {0} not found.").format(alert))
    if row.brand:
        perms.require_brand_access(frappe.session.user, row.brand)
    elif not perms.is_global_supervisor(frappe.session.user):
        frappe.throw(_("Only supervisors can view unmapped-brand evidence."),
                     frappe.PermissionError)
    rows = frappe.get_all(
        "EC Alert Occurrence", filters={"case": alert}, fields=OCC_FIELDS,
        order_by="detected_at desc, creation desc",
        start=cint(start), page_length=min(cint(page_len) or 50, MAX_PAGE))
    return {"rows": rows, "total": frappe.db.count("EC Alert Occurrence", {"case": alert})}


@frappe.whitelist()
def my_scope():
    """Allowed brands + role per brand for the UI (filter dropdown, defaults).
    Supervisors (System Manager) have implicit access to ALL brands, so we
    return the full active Brand Approver list for them too - otherwise the
    brand <select> in the policy/rule drawers would be blank (UAT bug)."""
    allowed = perms.require_alert_center_access()
    if allowed == perms.ALL_BRANDS:
        brands = {b: "supervisor" for b in frappe.get_all(
            "Brand Approver", filters={"status": "Active"}, pluck="name")}
        return {"supervisor": True, "brands": brands}
    return {"supervisor": False, "brands": allowed}

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

HANDLE_STATUSES = ("In Review", "Resolved", "Ignored")
NOTE_REQUIRED = ("Resolved", "Ignored")
MAX_PAGE = 100

LIST_FIELDS = [
    "name", "alert_type", "rule_code", "severity", "status", "title",
    "brand", "platform", "shop", "item", "seller_sku", "owner_user",
    "actual_price", "min_price", "baseline_price", "gap_percent",
    "recommended_action", "detected_at", "reference_doctype",
    "reference_name", "resolved_by", "resolved_at",
]


def _parse(filters):
    if isinstance(filters, str):
        filters = json.loads(filters or "{}")
    return filters or {}


def _scoped_filters(f, allowed):
    """Build frappe filter list; returns None when scope intersection is empty."""
    flt = []
    for k in ("status", "severity", "alert_type", "rule_code", "platform", "owner_user"):
        if f.get(k):
            flt.append([k, "=", f[k]])
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
        return frappe.db.count("EC Alert", f)

    open_states = {"status": ("in", ["Open", "In Review"])}
    af = {"action_type": "Stock Safety Lock", "status": ("in", ["Pending", "Dry Run"])}
    if scope is not None:
        af["brand"] = ("in", scope)
    return {
        "open": count(open_states),
        "critical": count(dict(open_states, severity="Critical")),
        "warning": count(dict(open_states, severity="Warning")),
        "missing_policy": count(dict(open_states,
                                     rule_code=("in", ["missing_policy", "missing_brand_mapping"]))),
        "lock_pending": frappe.db.count("EC Alert Action", af),
        "resolved_today": count({"status": "Resolved",
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
    if new_status in NOTE_REQUIRED and not (note and str(note).strip()):
        frappe.throw(_("A note is required to mark an alert {0}.").format(new_status))
    doc.status = new_status
    if note and str(note).strip():
        doc.resolution_note = str(note).strip()
    doc.save(ignore_permissions=True)  # controller stamps resolved_by/resolved_at
    return {"name": doc.name, "status": doc.status,
            "resolved_by": doc.resolved_by, "resolved_at": doc.resolved_at}


@frappe.whitelist()
def my_scope():
    """Allowed brands + role per brand for the UI (filter dropdown, defaults)."""
    allowed = perms.require_alert_center_access()
    if allowed == perms.ALL_BRANDS:
        return {"supervisor": True, "brands": {}}
    return {"supervisor": False, "brands": allowed}

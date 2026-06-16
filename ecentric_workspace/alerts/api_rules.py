"""Phase F - EC Alert Rule config (decision F-2: KAM drafts, Lead/SM activate)."""
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.alerts import permissions as perms

FIELDS = ["name", "rule_code", "status", "enabled", "brand", "platform", "shop",
          "item", "seller_sku", "severity_override", "threshold_percent",
          "recommend_stock_lock", "effective_from", "effective_to",
          "approved_by", "approved_at", "modified"]
EDITABLE = ["rule_code", "enabled", "brand", "platform", "shop", "item",
            "seller_sku", "severity_override", "threshold_percent",
            "recommend_stock_lock", "effective_from", "effective_to"]


@frappe.whitelist()
def list_rules(filters=None):
    allowed = perms.require_alert_center_access()
    f = json.loads(filters) if isinstance(filters, str) else (filters or {})
    flt = []
    for k in ("rule_code", "status", "platform", "shop", "seller_sku"):
        if f.get(k):
            flt.append([k, "=", f[k]])
    if allowed == perms.ALL_BRANDS:
        if f.get("brand"):
            flt.append(["brand", "=", f["brand"]])
    else:
        scope = [b for b in allowed if not f.get("brand") or b == f["brand"]]
        if not scope:
            return {"rows": []}
        flt.append(["brand", "in", scope])
    return {"rows": frappe.get_all("EC Alert Rule", filters=flt, fields=FIELDS,
                                   order_by="brand asc, rule_code asc, modified desc",
                                   limit_page_length=500)}


@frappe.whitelist(methods=["POST"])
def save_rule(rule=None, name=None):
    """KAM (and up) create/edit. Saving an ACTIVE rule demotes it to Draft
    unless the editor can activate - edits to live config always re-approve."""
    perms.require_alert_center_access()
    data = json.loads(rule) if isinstance(rule, str) else (rule or {})
    user = frappe.session.user
    if not data.get("brand"):
        frappe.throw(_("brand is required"))
    if not perms.can_manage_policy(user, data["brand"]):  # same edit tier as policy
        frappe.throw(_("You cannot manage rules of brand {0}.").format(data["brand"]),
                     frappe.PermissionError)
    if name:
        doc = frappe.get_doc("EC Alert Rule", name)
        if not perms.can_manage_policy(user, doc.brand):
            frappe.throw(_("Out of scope."), frappe.PermissionError)
    else:
        # RC5-4: find-or-update by SCOPE IDENTITY (brand + rule_code + platform +
        # shop + seller_sku + item) so the same logical override maps to ONE doc.
        # Without this, re-saving an override (or re-adding after "Bo tuy chinh"
        # paused it) created a DUPLICATE row, leaving the renderer / resolver with
        # two rows of the same identity (one Paused, one Draft) -> the row showed
        # "inherited" even though the save succeeded, and re-adding kept failing.
        existing = _find_rule_by_identity(data)
        doc = frappe.get_doc("EC Alert Rule", existing) if existing \
            else frappe.new_doc("EC Alert Rule")
    was_paused = (doc.status == "Paused")
    for k in EDITABLE:
        if k in data:
            doc.set(k, data[k])
    if doc.status == "Active" and not perms.can_activate_rule(user, doc.brand):
        doc.status = "Draft"          # edits to live rules require re-approval
        doc.approved_by = None
        doc.approved_at = None
    if was_paused:
        # RC5-4: re-adding a customization onto a previously-removed (Paused)
        # override RESUMES it for re-approval rather than leaving it paused (a
        # paused override is ignored by the resolver). KAMs draft; Lead/SM activate.
        doc.status = "Draft"
        doc.approved_by = None
        doc.approved_at = None
    if not doc.status:
        doc.status = "Draft"
    doc.save(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status}


def _norm(v):
    return (v or "")


def _find_rule_by_identity(data):
    """Return the name of the existing EC Alert Rule with the SAME scope identity
    as `data` (brand + rule_code + platform + shop + seller_sku + item), or None.
    Empty/None scope parts are normalized so '' and NULL compare equal. Used so a
    create-without-name never produces a duplicate of an existing (incl. Paused)
    rule of the same scope."""
    if not data.get("brand") or not data.get("rule_code"):
        return None
    cands = frappe.get_all(
        "EC Alert Rule",
        filters={"brand": data.get("brand"), "rule_code": data.get("rule_code"),
                 "platform": data.get("platform") or "All"},
        fields=["name", "shop", "seller_sku", "item"],
        order_by="creation asc", limit_page_length=0)
    for c in cands:
        if (_norm(c.shop) == _norm(data.get("shop"))
                and _norm(c.seller_sku) == _norm(data.get("seller_sku"))
                and _norm(c.item) == _norm(data.get("item"))):
            return c.name
    return None


@frappe.whitelist(methods=["POST"])
def set_rule_status(name, status):
    """Activate/Pause = approval step: manager/leader/System Manager only."""
    perms.require_alert_center_access()
    if status not in ("Draft", "Active", "Paused"):
        frappe.throw(_("Invalid status {0}").format(status))
    doc = frappe.get_doc("EC Alert Rule", name)
    user = frappe.session.user
    if status in ("Active", "Paused"):
        if not perms.can_activate_rule(user, doc.brand):
            frappe.throw(_("Only Lead/System Manager can activate or pause rules."),
                         frappe.PermissionError)
        if status == "Active":
            doc.approved_by = user
            doc.approved_at = now_datetime()
    elif not perms.can_manage_policy(user, doc.brand):
        frappe.throw(_("Out of scope."), frappe.PermissionError)
    doc.status = status
    doc.save(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status,
            "approved_by": doc.approved_by, "approved_at": str(doc.approved_at or "")}


@frappe.whitelist(methods=["POST"])
def check_rule_overlap(rule=None):
    """UI helper (approved requirement #2): for a prospective rule, report
    which broader/narrower Active rules of the same brand+rule_code exist, so
    the user sees what the new rule would override (SKU > Shop > Platform >
    Brand). Read-only."""
    perms.require_alert_center_access()
    data = json.loads(rule) if isinstance(rule, str) else (rule or {})
    if not data.get("brand") or not data.get("rule_code"):
        return {"overlaps": []}
    perms.require_brand_access(frappe.session.user, data["brand"])
    rows = frappe.get_all("EC Alert Rule",
                          filters={"brand": data["brand"], "rule_code": data["rule_code"],
                                   "status": "Active"},
                          fields=["name", "platform", "shop", "seller_sku", "item"])
    def tier(r):
        if r.get("seller_sku") or r.get("item"):
            return 4, "SKU"
        if r.get("shop"):
            return 3, "Shop"
        if r.get("platform") and r.get("platform") != "All":
            return 2, "Platform"
        return 1, "Brand"
    new_tier = tier(data)
    overlaps = []
    for r in rows:
        t = tier(r)
        relation = ("overridden_by_new" if t[0] < new_tier[0]
                    else "overrides_new" if t[0] > new_tier[0] else "same_tier")
        overlaps.append({"name": r.name, "tier": t[1], "relation": relation})
    return {"new_tier": new_tier[1], "overlaps": overlaps,
            "priority": "SKU > Shop > Platform > Brand"}

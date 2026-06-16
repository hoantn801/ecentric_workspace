"""RC7-C Gift/Freebie Price Guard exemption API (V1: dedicated gift Seller SKUs).
Brand-scoped, whitelisted CRUD. No hard delete in V1 (operators inactivate instead;
permanent deletion, if ever added, must follow the same safe-delete contract as
EC Price Policy). The DocType controller enforces uniqueness/overlap on save."""
import json

import frappe
from frappe import _

from ecentric_workspace.alerts import permissions as perms

FIELDS = ["name", "brand", "platform", "seller_sku", "reason", "status",
          "effective_from", "effective_to", "notes", "exempted_by", "modified"]
EDITABLE = ["brand", "platform", "seller_sku", "reason", "status",
            "effective_from", "effective_to", "notes"]


@frappe.whitelist()
def list_exemptions(filters=None):
    allowed = perms.require_alert_center_access()
    f = json.loads(filters) if isinstance(filters, str) else (filters or {})
    flt = []
    for k in ("platform", "status", "seller_sku"):
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
    return {"rows": frappe.get_all("EC Price Guard Exemption", filters=flt,
                                   fields=FIELDS, order_by="modified desc",
                                   limit_page_length=200)}


@frappe.whitelist(methods=["POST"])
def save_exemption(exemption=None, name=None):
    perms.require_alert_center_access()
    data = json.loads(exemption) if isinstance(exemption, str) else (exemption or {})
    if not data.get("brand"):
        frappe.throw(_("brand is required"))
    perms.require_brand_access(frappe.session.user, data["brand"])
    if name:
        doc = frappe.get_doc("EC Price Guard Exemption", name)
        perms.require_brand_access(frappe.session.user, doc.brand)
    else:
        doc = frappe.new_doc("EC Price Guard Exemption")
    for k in EDITABLE:
        if k in data:
            doc.set(k, data[k])
    doc.save(ignore_permissions=True)        # controller validates overlap/window
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def set_exemption_status(name, status):
    perms.require_alert_center_access()
    if status not in ("Active", "Inactive"):
        frappe.throw(_("Invalid status {0}").format(status))
    doc = frappe.get_doc("EC Price Guard Exemption", name)
    perms.require_brand_access(frappe.session.user, doc.brand)
    doc.status = status
    doc.save(ignore_permissions=True)        # re-validates overlap when -> Active
    return {"name": doc.name, "status": doc.status}

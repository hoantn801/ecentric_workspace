"""Alert Center UI endpoints - EC Alert Action, READ-ONLY in Phase E.
No retry/cancel/release endpoints exist in this phase (dry-run era; execution
control stays System Manager only and outside the UI)."""
import frappe
from frappe import _

from ecentric_workspace.alerts import permissions as perms

FIELDS = ["name", "alert", "action_type", "status", "brand", "platform",
          "shop", "item", "seller_sku", "external_product_id",
          "previous_available_stock", "lock_until", "lock_reason",
          "release_status", "requested_at", "executed_at", "executed_by",
          "api_response", "error_message",
          # Phase F: review workflow + DS1 audit (placeholders until gate)
          "review_status", "reviewed_by", "reviewed_at", "review_note",
          "actual_stock_before", "available_stock_before",
          "buffer_stock_before", "buffer_stock_after", "locked_quantity",
          "release_required", "release_strategy"]


@frappe.whitelist()
def list_for_alert(alert):
    perms.require_alert_center_access()
    brand = frappe.db.get_value("EC Alert", alert, "brand")
    if brand:
        perms.require_brand_access(frappe.session.user, brand)
    elif not perms.is_global_supervisor():
        frappe.throw(_("Only supervisors can view actions of unmapped-brand alerts."),
                     frappe.PermissionError)
    return frappe.get_all("EC Alert Action", filters={"alert": alert},
                          fields=FIELDS, order_by="creation desc",
                          limit_page_length=50)


@frappe.whitelist()
def list_actions(filters=None, start=0, page_len=50):
    """Phase F locks page: scoped action list (beyond per-alert)."""
    import json as _json
    from frappe.utils import cint
    allowed = perms.require_alert_center_access()
    f = _json.loads(filters) if isinstance(filters, str) else (filters or {})
    flt = [["action_type", "=", "Stock Safety Lock"]]
    for k in ("status", "review_status", "platform", "shop"):
        if f.get(k):
            flt.append([k, "=", f[k]])
    if f.get("seller_sku"):
        flt.append(["seller_sku", "like", "%%%s%%" % f["seller_sku"]])
    if allowed == perms.ALL_BRANDS:
        if f.get("brand"):
            flt.append(["brand", "=", f["brand"]])
    else:
        scope = [b for b in allowed if not f.get("brand") or b == f["brand"]]
        if not scope:
            return {"rows": [], "total": 0}
        flt.append(["brand", "in", scope])
    rows = frappe.get_all("EC Alert Action", filters=flt, fields=FIELDS,
                          order_by="creation desc", start=cint(start),
                          page_length=min(cint(page_len) or 50, 100))
    return {"rows": rows, "total": frappe.db.count("EC Alert Action", filters=flt)}


@frappe.whitelist(methods=["POST"])
def review_action(name, decision, note=None):
    """Phase F DRY-RUN review: Approve keeps status=Dry Run (stamps audit);
    Reject -> status=Cancelled + note REQUIRED. This is a review of a
    SIMULATION - no Omisell call exists or happens here (DS1 locked). The
    future real executor will act only on review_status=Approved."""
    from frappe.utils import now_datetime
    perms.require_alert_center_access()
    if decision not in ("Approve", "Reject"):
        frappe.throw(_("Invalid decision {0}").format(decision))
    doc = frappe.get_doc("EC Alert Action", name)
    if not perms.can_review_lock(frappe.session.user, doc.brand):
        frappe.throw(_("You cannot review lock actions of brand {0}.").format(doc.brand),
                     frappe.PermissionError)
    if doc.status not in ("Dry Run", "Pending", "Skipped"):
        frappe.throw(_("Only dry-run-era actions can be reviewed (status {0}).").format(doc.status))
    if decision == "Reject" and not (note and str(note).strip()):
        frappe.throw(_("A note is required to reject."))
    doc.review_status = "Approved" if decision == "Approve" else "Rejected"
    doc.reviewed_by = frappe.session.user
    doc.reviewed_at = now_datetime()
    if note and str(note).strip():
        doc.review_note = str(note).strip()
    if decision == "Reject":
        doc.status = "Cancelled"
    doc.save(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status,
            "review_status": doc.review_status,
            "reviewed_by": doc.reviewed_by, "reviewed_at": str(doc.reviewed_at)}

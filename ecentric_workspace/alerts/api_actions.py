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
          "api_response", "error_message"]


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

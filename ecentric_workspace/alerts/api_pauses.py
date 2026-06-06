"""Alert Center UI endpoints - EC Automation Pause (brand-scoped).
create = kam/manager of that brand; cancel = manager/leader; never deleted."""
import frappe
from frappe import _

from ecentric_workspace.alerts import permissions as perms


@frappe.whitelist(methods=["POST"])
def create_pause(brand, pause_from, pause_until, reason=None, platform="All",
                 shop=None, item=None, seller_sku=None):
    perms.require_alert_center_access()
    user = frappe.session.user
    if not perms.can_create_pause(user, brand):
        frappe.throw(_("You cannot pause automation for brand {0}.").format(brand),
                     frappe.PermissionError)
    doc = frappe.get_doc({
        "doctype": "EC Automation Pause",
        "automation_type": "Stock Safety Lock",
        "brand": brand, "platform": platform or "All",
        "shop": shop, "item": item, "seller_sku": seller_sku,
        "pause_from": pause_from, "pause_until": pause_until,
        "reason": reason, "status": "Active",
    })
    doc.insert(ignore_permissions=True)  # controller: window sanity + paused_by
    return {"name": doc.name, "status": doc.status, "paused_by": doc.paused_by}


@frappe.whitelist(methods=["POST"])
def cancel_pause(name):
    perms.require_alert_center_access()
    doc = frappe.get_doc("EC Automation Pause", name)
    if not perms.can_cancel_pause(frappe.session.user, doc.brand):
        frappe.throw(_("You cannot cancel pauses of brand {0}.").format(doc.brand),
                     frappe.PermissionError)
    doc.status = "Cancelled"
    doc.save(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def list_pauses(active_only=0):
    allowed = perms.require_alert_center_access()
    filters = {}
    if allowed != perms.ALL_BRANDS:
        filters["brand"] = ("in", list(allowed))
    if int(active_only or 0):
        filters["status"] = "Active"
    return frappe.get_all(
        "EC Automation Pause", filters=filters,
        fields=["name", "brand", "platform", "shop", "item", "seller_sku",
                "pause_from", "pause_until", "status", "paused_by", "reason"],
        order_by="pause_until desc", limit_page_length=200)

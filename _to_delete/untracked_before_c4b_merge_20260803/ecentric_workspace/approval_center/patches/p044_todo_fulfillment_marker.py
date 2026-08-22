# Copyright (c) 2026, eCentric and contributors
"""Phase 1b.3.1b: add the stable fulfillment-action marker (Custom Field
`ec_fulfillment` on ToDo) so fulfillment lifecycle operations can scope to
fulfillment tasks only (never touching unrelated ToDos on the same business
document), then run the idempotent reconciliation for existing active fulfillment
records that were claimed before this batch.

Idempotent: the Custom Field is created once; reconciliation is safe to re-run
(a second execute() makes no ToDo changes). Reports before/after counts.
"""
import frappe

FIELD = {
    "fieldname": "ec_fulfillment",
    "label": "EC Fulfillment Task",
    "fieldtype": "Check",
    "default": "0",
    "hidden": 1,
    "no_copy": 1,
    "read_only": 1,
    "description": ("Approval Center (engine-owned): marks a ToDo as a "
                    "fulfillment-stage task. Do not edit manually."),
}


def _ensure_custom_field(dt, df):
    name = dt + "-" + df["fieldname"]
    if frappe.db.exists("Custom Field", name):
        return False
    payload = {"doctype": "Custom Field", "dt": dt}
    payload.update(df)
    frappe.get_doc(payload).insert(ignore_permissions=True)
    return True


def execute():
    created = _ensure_custom_field("ToDo", FIELD)
    if created:
        frappe.clear_cache(doctype="ToDo")
    from ecentric_workspace.approval_center.engine.service import reconcile_fulfillment_todos
    res = reconcile_fulfillment_todos()
    msg = ("[1b.3.1b] fulfillment ToDo reconcile (marker created=%s): "
           "open fulfillment ToDos %s -> %s across %d DocTypes"
           % (created, res.get("before"), res.get("after"), len(res.get("doctypes") or [])))
    frappe.logger().info(msg)
    print(msg)

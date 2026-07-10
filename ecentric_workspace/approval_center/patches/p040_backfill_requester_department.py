# Copyright (c) 2026, eCentric and contributors
"""Best-effort historical backfill of EC Approval Request.requester_department.

Idempotent: only touches rows where the snapshot is still blank. Uses the SAME governed
resolver as submit (engine.resolve_requester_department). If a governed source cannot be
resolved, the row is LEFT BLANK (never guessed). Never edits business documents or
workflow state. Safe to re-run."""
import frappe

from ecentric_workspace.approval_center.engine.service import resolve_requester_department


def execute():
    if not frappe.db.has_column("EC Approval Request", "requester_department"):
        return
    rows = frappe.get_all("EC Approval Request",
                          filters={"requester_department": ["in", [None, ""]]},
                          fields=["name", "requested_by", "reference_doctype", "reference_name"])
    filled = 0
    for r in rows:
        dept = resolve_requester_department(r.requested_by, r.reference_doctype, r.reference_name)
        if dept:
            frappe.db.set_value("EC Approval Request", r.name, "requester_department", dept,
                                update_modified=False)
            filled += 1
    frappe.db.commit()
    frappe.logger().info("p040 backfill requester_department: %d of %d filled, %d left blank"
                         % (filled, len(rows), len(rows) - filled))

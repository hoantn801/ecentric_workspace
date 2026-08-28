# Copyright (c) 2026, eCentric and contributors
"""Level 1 of PAYMENT_REQUEST asked two sources for one answer, and they disagreed.

The level carried "Department Manager" (dynamic) AND "Requester Manager" (reports_to). For
ordinary staff both name the same person and the duplicate folds away. For a department head
they diverge: himself, and his own manager one level up - a CEO.

eContract's "Truong bo phan" step does not accept a CEO. Every Payment Request on 2026-08-28
therefore went out to the whole role pool: seven department heads notified instead of the one
named person. The signing side dropped the ineligible recipient and recorded it
(`dropped_not_eligible`), which is how this was found.

Removing the row is only safe because its purpose - never leaving a requester without an
approver - now lives inside the Department Manager source itself: when that source resolves
nobody, the level opens to the pool of department heads (labelled "Department Manager Pool").
So the safety net still exists; it just no longer fires for people who DO have a manager.

Idempotent: the row is matched on source_type and deleted only if present.
"""
import frappe

PROCESS = "PAYMENT_REQUEST-V1"
LEVEL_NO = 1
DROP_SOURCE = "Requester Manager"


def execute():
    levels = frappe.get_all("EC Approval Level",
                            filters={"approval_process": PROCESS, "level_no": LEVEL_NO},
                            fields=["name"], limit_page_length=0)
    if not levels:
        frappe.logger().info("p100: %s level %s absent, nothing to do" % (PROCESS, LEVEL_NO))
        return

    for lvl in levels:
        doc = frappe.get_doc("EC Approval Level", lvl.name)
        rows = getattr(doc, "participants", None) or []
        keep, dropped = [], []
        for r in rows:
            if (r.source_type == DROP_SOURCE
                    and (r.participant_purpose or "Approver") == "Approver"):
                dropped.append(r)
            else:
                keep.append(r)
        if not dropped:
            frappe.logger().info("p100: %s already has no %s row" % (lvl.name, DROP_SOURCE))
            continue
        # Refuse to leave the level with no approver source at all - that would block every
        # submission. Better to change nothing and stay visible than to break submitting.
        if not keep:
            frappe.logger().error(
                "p100: refusing to empty %s - it would leave the level with no approver "
                "source and block every Payment Request" % lvl.name)
            continue
        doc.set("participants", keep)
        doc.save(ignore_permissions=True)
        frappe.logger().info("p100: removed %d '%s' row(s) from %s"
                             % (len(dropped), DROP_SOURCE, lvl.name))

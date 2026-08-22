# Copyright (c) 2026, eCentric and contributors
"""PAYMENT_REQUEST L1 'Direct Manager Review': add a 'Department Manager' approver candidate
(Any One) alongside the existing 'Requester Manager'.

Business rule (user directive 2026-08-23): when the requester IS the department head, L1 should
be signable by the requester themselves (they sign the 'Truong bo phan' area) instead of
escalating to their reports_to (the CEO) - which also made the CEO a duplicate approver at L1+L4
and, under the duplicate-approver auto-skip, left the CEO sign AREA orphaned on the SCTS
document. For regular staff the department head and the direct manager usually coincide, so the
Any-One candidate pool is unchanged in practice.

Resolution source: Department.department_head -> Employee.user_id (the same governed path the
engine's 'Department Manager' source_type already implements; fail-closed when unset).
Idempotent: skipped when the row already exists. Frozen (already-submitted) requests keep their
snapshot - this affects NEW submissions only."""
import frappe

PROCESS = "PAYMENT_REQUEST-V1"


def execute():
    names = frappe.get_all("EC Approval Level",
                           filters={"approval_process": PROCESS, "level_no": 1}, pluck="name")
    if not names:
        return
    lvl = frappe.get_doc("EC Approval Level", names[0])
    for p in (lvl.participants or []):
        if p.source_type == "Department Manager" and p.participant_purpose == "Approver":
            return                                    # already applied
    lvl.append("participants", {"participant_purpose": "Approver",
                                "source_type": "Department Manager", "sort_order": -1})
    lvl.save(ignore_permissions=True)

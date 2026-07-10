# Copyright (c) 2026, eCentric and contributors
"""Indexes justified by the dashboard query patterns (scope + filter + grouping).
Idempotent: frappe.db.add_index is a no-op if the index already exists."""
import frappe


def execute():
    frappe.db.add_index("EC Approval Request",
                        ["approval_status", "approval_type"], index_name="ec_apr_status_type")
    frappe.db.add_index("EC Approval Request", ["requester_department"], index_name="ec_apr_req_dept")
    frappe.db.add_index("EC Approval Request", ["requested_by"], index_name="ec_apr_requested_by")
    frappe.db.add_index("EC Approval Request", ["submitted_at"], index_name="ec_apr_submitted_at")
    frappe.db.add_index("EC Approval Request Approver",
                        ["approver", "status"], index_name="ec_apra_approver_status")

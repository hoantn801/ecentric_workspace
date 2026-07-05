# Copyright (c) 2026, eCentric and contributors
"""p010_create_document_request_page: create the Document Request Web Page at route
/approvals/document-request from source (run-once at migrate). Delegates to
document_request.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.document_request import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p010_create_document_request_page: %s" % (res or {}))

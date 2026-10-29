# Copyright (c) 2026, eCentric and contributors
"""Hang so cho gbs_attachments. Khong co bi mat o day."""

#: DocType ben EC -> DocType ben boxme.
BOXME_DOCTYPE = {
    "GBS Sales Order": "Sales Order",
    "GBS Purchase Order": "Purchase Order",
}

#: Dau hieu mot file_url ben boxme la link SharePoint (bi boxme auto-reject).
SHAREPOINT_HOST_MARK = "sharepoint.com"

#: Boxme khong noi gioi han; file lon hon muc nay ghi loi ro rang thay vi treo job.
MAX_FILE_BYTES = 25 * 1024 * 1024

GRAPH = "https://graph.microsoft.com/v1.0"
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 120

JOB_METHOD = "ecentric_workspace.gbs_attachments.jobs.push_job.run"
JOB_QUEUE = "long"
JOB_TIMEOUT = 1200
LOCK_SECONDS = 1200

#: Su kien ghi vao approval_history (audit).
HISTORY_EVENT = "attachments_original_push"

#: Role duoc goi preview / day tay (ngoai quyen doc phieu).
ADMIN_ROLES = ("System Manager",)

#: Hanh dong workflow ben boxme (giong Server Script sync v11/v12).
ACTION_RESUBMIT = "Resubmit"
ACTION_SO_SUBMIT = "Submit for Approval"
ACTION_PO_SUBMIT = "Submit"
RESUBMIT_EVENT = "gbs_resubmit_after_file_fix"

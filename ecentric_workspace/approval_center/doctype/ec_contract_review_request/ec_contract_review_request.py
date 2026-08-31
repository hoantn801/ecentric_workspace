# Copyright (c) 2026, eCentric and contributors
"""EC Contract Review Request - business data only; approval STATE lives on
EC Approval Request. Thay thế SharePoint list Finance2/Contract approval.
request_kind quyết định số cấp duyệt (Existing: 3 cấp + CC CEO; New: đủ 4 cấp)
- logic đó nằm ở application/service.py, không nằm đây."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECContractReviewRequest(Document):
    def validate(self):
        self._snapshot_lock()

    def _snapshot_lock(self):
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if not before:
            return
        for f in ("department", "request_kind", "previous_request"):
            if before.get(f) and before.get(f) != self.get(f):
                frappe.throw(_("Truong nay la ban chup luc gui va khong the thay doi sau khi gui."))

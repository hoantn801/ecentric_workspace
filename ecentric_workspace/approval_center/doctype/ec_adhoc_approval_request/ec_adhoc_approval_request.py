# Copyright (c) 2026, eCentric and contributors
"""EC Adhoc Approval Request - Phe duyet dot xuat gui CEO (phieu rieng tu). Logic nghiep vu o
features/adhoc_approval/application/service.py; DocType chi luu du lieu.

validate (23/11/2026): noi dung soan kieu mail `content_html` LUON duoc loc o day (moi duong ghi),
`content` (chu tran) suy ra tu no - dung cho tim kiem / tom tat / kiem bat buoc."""
from frappe.model.document import Document

from ecentric_workspace.approval_center.shared import rich_text


class ECAdhocApprovalRequest(Document):
    def validate(self):
        if self.get("content_html"):
            self.content_html = rich_text.safe_html(self.content_html)
            self.content = rich_text.to_text(self.content_html) or None

# Copyright (c) 2026, eCentric and contributors
"""EC Approval Request Approver - runtime per-approver state (NOT the audit log).
Directly queryable for 'Can toi duyet'. Unique approver per request level - EXCEPT Each Group:
mot nguoi co the dai dien HAI nhom cua cung mot cap (vd vua giu role HR vua HOF). Engine da
thiet ke cho truong hop nay (transitions.approve: bam mot lan xac nhan ca cac nhom cua minh),
nhung validate cu chan trung theo (cap, nguoi) -> snapshot New Staff Preparation hong "Duplicate
approver ..." ngay khi co nguoi giu role o 2 nhom: 10/10 Offer thang 10 khong sinh NSP (tim ra
24/11/2026 bang phieu test). Nay: khoa trung theo (cap, nguoi, nhom)."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECApprovalRequestApprover(Document):
    def validate(self):
        filters = {"request_level": self.request_level, "approver": self.approver,
                   "name": ["!=", self.name or ""]}
        group = (self.get("participant_group") or "").strip()
        rows = frappe.get_all("EC Approval Request Approver", filters=filters,
                              fields=["name", "participant_group"])
        if any((r.get("participant_group") or "").strip() == group for r in rows):
            frappe.throw(_("Duplicate approver {0} for this request level.").format(self.approver))

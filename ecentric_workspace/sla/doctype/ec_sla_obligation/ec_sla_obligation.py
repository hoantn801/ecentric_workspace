# Copyright (c) 2026, eCentric and contributors
"""EC SLA Obligation - mot dau viec duoc cham diem.

Controller CHU Y KHONG chua logic cham diem. Nghia vu duoc mo/dong/loai tru duy
nhat qua `application.obligation_service`; day chi la lop chan cuoi cung de mot
ban ghi hong khong loi vao DB qua duong khac (Desk, data import, script cu).

Khong xoa duoc: diem cua mot nguoi phai co the truy nguoc. Muon go thi
`Cancelled`, co dau vet, khong phai `DELETE`.
"""
import frappe
from frappe import _
from frappe.model.document import Document

from ecentric_workspace.sla.constants import ALL_GROUPS, ALL_STATUSES, STATUS_OPEN


class ECSLAObligation(Document):
    def validate(self):
        if self.status not in ALL_STATUSES:
            frappe.throw(_("status '{0}' khong hop le.").format(self.status))
        if self.group_key not in ALL_GROUPS:
            frappe.throw(_("group_key '{0}' khong hop le.").format(self.group_key))
        if not self.dedupe_key:
            frappe.throw(_("dedupe_key la bat buoc."))
        if not self.period_month or len(self.period_month) != 7:
            frappe.throw(_("period_month phai co dang YYYY-MM."))
        if self.closed_at and self.opened_at and self.closed_at < self.opened_at:
            frappe.throw(_("closed_at khong the truoc opened_at."))
        if self.status != STATUS_OPEN and self.is_breached:
            # `is_breached` chi co nghia khi con mo. De lai co nay tren mot dong
            # da dong se lam mau so bi dem hai lan trong bao cao doc thang cot.
            self.is_breached = 0

    def on_trash(self):
        frappe.throw(_("Khong xoa duoc nghia vu SLA. Dung trang thai Cancelled de giu dau vet."))

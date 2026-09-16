# Copyright (c) 2026, eCentric and contributors
"""EC SLA Adjustment - dau vet cua moi lan doi diem bang tay.

Ban ghi nay bat bien sau khi tao. Mot nhat ky sua duoc khong phai la nhat ky.
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from ecentric_workspace.sla.constants import ALL_ADJUSTMENTS, ADJ_EXTEND_DUE


class ECSLAAdjustment(Document):
    def validate(self):
        if self.action not in ALL_ADJUSTMENTS:
            frappe.throw(_("action '{0}' khong hop le.").format(self.action))
        if not (self.reason or "").strip():
            frappe.throw(_("Phai ghi ly do dieu chinh."))
        if self.action == ADJ_EXTEND_DUE and not self.new_due_at:
            frappe.throw(_("Hanh dong {0} can han moi.").format(ADJ_EXTEND_DUE))
        if self.is_new():
            self.adjusted_by = self.adjusted_by or frappe.session.user
            self.adjusted_at = self.adjusted_at or now_datetime()
        else:
            frappe.throw(_("Ban ghi dieu chinh khong sua duoc. Tao ban ghi moi de dao nguoc."))

    def on_trash(self):
        frappe.throw(_("Khong xoa duoc ban ghi dieu chinh SLA."))

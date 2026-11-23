# Copyright (c) 2026, eCentric and contributors
"""EC Discipline Decision Request - phieu engine cho buoc CEO ky quyet dinh ky luat.

Ban chup cua EC Discipline Case luc HR trinh; chi sua lai duoc qua hr/ky_luat khi CEO yeu cau
bo sung (features/discipline_decision/application/service.gui_lai_tu_ho_so)."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECDisciplineDecisionRequest(Document):
    def validate(self):
        if self.is_new() or not self.approval_request or frappe.flags.get("ec_discipline_resubmit") \
                or frappe.flags.in_patch:
            return
        before = self.get_doc_before_save()
        if before and before.get("discipline_case") != self.get("discipline_case"):
            frappe.throw(_("Không đổi được hồ sơ gốc của phiếu quyết định."))

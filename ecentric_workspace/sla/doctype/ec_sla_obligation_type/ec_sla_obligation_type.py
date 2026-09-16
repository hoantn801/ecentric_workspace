# Copyright (c) 2026, eCentric and contributors
"""EC SLA Obligation Type - danh muc loai nghia vu. Controller mong, chi validate."""
import frappe
from frappe import _
from frappe.model.document import Document

from ecentric_workspace.sla.constants import ALL_GROUPS, DT_OBLIGATION


class ECSLAObligationType(Document):
    def validate(self):
        if self.group_key not in ALL_GROUPS:
            frappe.throw(_("group_key '{0}' khong hop le.").format(self.group_key))
        if not self.is_new():
            before = self.get_doc_before_save()
            if before and before.type_code and before.type_code != self.type_code:
                frappe.throw(_("type_code la bat bien."))
            # Doi nhom cua mot loai da co du lieu se lam lech moi bao cao lich su:
            # nghia vu cu giu group_key da chup, nghia vu moi mang nhom moi, va
            # bang diem cua cung mot nguoi tach lam doi ma khong ai giai thich
            # duoc. Chan tai day, khong de phat hien sau khi da chot luong.
            if before and before.group_key and before.group_key != self.group_key:
                used = frappe.db.count(DT_OBLIGATION, {"obligation_type": self.name})
                if used:
                    frappe.throw(_("Khong doi duoc nhom: da co {0} nghia vu dung loai nay. "
                                   "Tao loai moi va tat loai cu.").format(used))
        if self.min_sample is not None and int(self.min_sample) < 0:
            frappe.throw(_("min_sample khong duoc am."))

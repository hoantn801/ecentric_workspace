# Copyright (c) 2026, eCentric and contributors
"""EC Asset Event - nhat ky thiet bi, CHI THEM. Sua / xoa mot dong da ghi bi chan (ke ca qua Desk):
dau vet la noi dung hang nhat cua module (quy uoc Auditability). Ghi qua tai_san.repository."""
import frappe
from frappe.model.document import Document

# Truong duy nhat duoc dien SAU khi ghi: nhan vien bam "Da nhan may".
_MUTABLE = ("acknowledged_at", "modified", "modified_by")


class ECAssetEvent(Document):
    def validate(self):
        if self.is_new():
            return
        before = self.get_doc_before_save()
        if not before:
            return
        for df in self.meta.fields:
            if df.fieldname in _MUTABLE:
                continue
            if self.get(df.fieldname) != before.get(df.fieldname):
                frappe.throw("Nhật ký thiết bị không sửa được (trường %s)." % df.label)

    def on_trash(self):
        frappe.throw("Nhật ký thiết bị không xoá được.")

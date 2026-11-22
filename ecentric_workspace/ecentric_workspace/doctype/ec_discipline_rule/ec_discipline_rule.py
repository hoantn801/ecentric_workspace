# Copyright (c) 2026, eCentric and contributors
"""EC Discipline Rule - danh muc dieu khoan noi quy (HR sua tren Desk). CRUD thuan, khong luat
nghiep vu, khong goi ngoai -> khong tach service (frappe-rules muc 11)."""
from frappe.model.document import Document


class ECDisciplineRule(Document):
    def validate(self):
        self.code = (self.code or "").strip()
        self.title = (self.title or "").strip()

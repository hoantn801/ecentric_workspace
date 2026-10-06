# Copyright (c) 2026, eCentric and contributors
"""EC Post Category - chuyen muc Tin noi bo. CRUD thuan (khong quy tac nghiep vu)."""
import re

import frappe
from frappe import _
from frappe.model.document import Document

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ECPostCategory(Document):
    # CRUD thuan: chi kiem dinh dang ma (ma la mot phan URL ?chuyen-muc=).
    def validate(self):
        self.slug = (self.slug or "").strip().lower()
        if not _SLUG_RE.match(self.slug):
            frappe.throw(_("Mã chuyên mục chỉ gồm chữ thường không dấu, số và gạch ngang (vd: thong-bao)."))

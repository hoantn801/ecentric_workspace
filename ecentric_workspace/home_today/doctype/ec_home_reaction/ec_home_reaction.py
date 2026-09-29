# Copyright (c) 2026, eCentric and contributors
"""EC Home Reaction - mot luot tha cam xuc tren popup trang chu. CRUD thuan: moi quy tac
(target hop le, bat/tat) nam o home_today.service; controller chi giu khoa chong trung."""
from frappe.model.document import Document


class ECHomeReaction(Document):
    def validate(self):
        self.dedupe_key = "%s|%s|%s" % (self.target, self.kind, self.user)

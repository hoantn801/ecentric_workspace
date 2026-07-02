# Copyright (c) 2026, eCentric and contributors
"""EC Approval Category controller (Approval Center B1).

Schema layer only. Enforces the immutable UPPER_SNAKE category_code
server-side (not merely via read-only metadata).
"""
import re

import frappe
from frappe import _
from frappe.model.document import Document

CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,49}$")


class ECApprovalCategory(Document):
    def validate(self):
        self._normalize_and_check_code()
        self._guard_immutable_code()

    def _normalize_and_check_code(self):
        if self.category_code:
            self.category_code = self.category_code.strip()
        if not self.category_code or not CODE_RE.match(self.category_code):
            frappe.throw(
                _("category_code must match ^[A-Z][A-Z0-9_]{{1,49}}$ (got: {0}).").format(
                    self.category_code
                )
            )

    def _guard_immutable_code(self):
        if self.is_new():
            return
        before = self.get_doc_before_save()
        if before and before.category_code and before.category_code != self.category_code:
            frappe.throw(_("category_code is immutable and cannot be changed once created."))

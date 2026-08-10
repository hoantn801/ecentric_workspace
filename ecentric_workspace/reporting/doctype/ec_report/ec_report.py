# Copyright (c) 2026, eCentric and contributors
"""EC Report -- one catalog card in the Reports Center hub (/reports).

Config only: it decides how a report appears on the hub and (for UX) who sees
the card. It is NEVER the data security boundary -- each destination report page
(e.g. /pnl-dashboard) enforces its own backend permission. Managed in Desk by
System Manager (see DocPerm)."""
import re

import frappe
from frappe import _
from frappe.model.document import Document

_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,49}$")


class ECReport(Document):
    def validate(self):
        code = (self.report_code or "").strip()
        if not _CODE_RE.match(code):
            frappe.throw(_("Report Code must be UPPER_SNAKE (A-Z, 0-9, _), 2-50 chars."))
        self.report_code = code

        # code is the record name and must never change after insert
        if not self.is_new():
            before = self.get_doc_before_save()
            if before and before.report_code != self.report_code:
                frappe.throw(_("Report Code cannot be changed once created."))

        route = (self.route or "").strip()
        self.route = route
        is_external = route.startswith("http://") or route.startswith("https://")
        if self.card_status == "Active":
            if not route or not (route.startswith("/") or is_external):
                frappe.throw(_("An Active card needs a Route starting with '/' "
                               "or a full https:// URL (external tool)."))
        # external tools always open in a new tab
        if is_external:
            self.open_new_tab = 1

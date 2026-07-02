# Copyright (c) 2026, eCentric and contributors
"""EC Approval Type controller (Approval Center B1).

Catalog/registry of approval types. Schema + validation layer only:
no list API, no workflow, no approval request (later phases).

Guards enforced server-side:
  * approval_code: UPPER_SNAKE regex + IMMUTABLE after insert (integration key).
  * route: required + must start with '/' when card_status == Active;
           '/approval' (existing inbox) is reserved and rejected.
  * allowed_roles / allowed_departments: de-duplicated.
Empty Restricted-* child tables are allowed here (fail-safe = the future
service layer returns no card); they are NOT a validation error.
"""
import re

import frappe
from frappe import _
from frappe.model.document import Document

CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,49}$")
RESERVED_ROUTES = {"/approval"}


class ECApprovalType(Document):
    def validate(self):
        self._normalize_and_check_code()
        self._guard_immutable_code()
        self._validate_route()
        self._dedupe_children()

    def _normalize_and_check_code(self):
        if self.approval_code:
            self.approval_code = self.approval_code.strip()
        if not self.approval_code or not CODE_RE.match(self.approval_code):
            frappe.throw(
                _("approval_code must match ^[A-Z][A-Z0-9_]{{1,49}}$ (got: {0}).").format(
                    self.approval_code
                )
            )

    def _guard_immutable_code(self):
        if self.is_new():
            return
        before = self.get_doc_before_save()
        if before and before.approval_code and before.approval_code != self.approval_code:
            frappe.throw(
                _("approval_code is an immutable integration key and cannot be changed once created.")
            )

    def _validate_route(self):
        route = (self.route or "").strip()
        self.route = route
        if self.card_status == "Active":
            if not route:
                frappe.throw(_("route is required when card_status is Active."))
            if not route.startswith("/"):
                frappe.throw(_("route must start with '/' (got: {0}).").format(route))
        if route and route.rstrip("/") in RESERVED_ROUTES:
            frappe.throw(
                _("route '{0}' is reserved for the existing approval inbox and cannot be assigned to an approval type.").format(route)
            )

    def _dedupe_children(self):
        seen = set()
        kept = []
        for r in (self.allowed_roles or []):
            if r.role and r.role not in seen:
                seen.add(r.role)
                kept.append(r)
        self.set("allowed_roles", kept)

        seen = set()
        kept = []
        for d in (self.allowed_departments or []):
            if d.department and d.department not in seen:
                seen.add(d.department)
                kept.append(d)
        self.set("allowed_departments", kept)

# Copyright (c) 2026, eCentric
# Alert Center. Schema/controller layer. Lifecycle rules (active vs terminal,
# allowed transitions, evidence freeze) come from services.case_lifecycle -
# the single source of truth (Step 1, 2026-06-13).

import frappe
from frappe import _
from frappe.model.document import Document

from ecentric_workspace.alerts.services import case_lifecycle as cl
from ecentric_workspace.alerts.services import case_todo


class ECAlert(Document):
    def validate(self):
        self._guard_no_reopen()
        self._guard_terminal_evidence_frozen()
        self._stamp_resolution()

    # ----- Step 2: Frappe ToDo lifecycle (single chokepoint) ----------------
    def after_insert(self):
        # A new case (engine / legacy / repair-split / Desk) -> ensure its ToDo.
        case_todo.sync_todo(self)

    def on_update(self):
        # Only sync when status or owner_user actually changed - NOT for
        # occurrence_count / evidence-only updates (e.g. _bump_case). This also
        # avoids needless work when assign_to touches _assign (recursion guard
        # in case_todo is the hard stop; this is the cheap pre-check).
        before = self.get_doc_before_save()
        if before is None:
            return
        if before.status != self.status or before.get("owner_user") != self.get("owner_user"):
            case_todo.sync_todo(self)

    # ----- lifecycle guards (defense-in-depth; APIs guard too) --------------
    def _guard_no_reopen(self):
        """A terminal case (Closed/Ignored/Cancelled/legacy Resolved) must not
        return to an active state in this phase - there is NO approved admin
        recovery/reopen flow. Engine never reopens (it creates a NEW case);
        this blocks a stray Desk/API edit."""
        before = self.get_doc_before_save()
        if not before:
            return
        if cl.is_terminal(before.status) and cl.is_active(self.status):
            frappe.throw(
                _("Case {0} is {1} (terminal) and cannot be reopened. A new "
                  "violation creates a new case.").format(self.name, before.status),
                frappe.ValidationError)

    def _guard_terminal_evidence_frozen(self):
        """Once terminal, evidence rollups freeze: occurrence_count and the
        first/last occurrence timestamps must not change. Blocks any path
        (normal or repair) from mutating a frozen case's evidence."""
        before = self.get_doc_before_save()
        if not before or not cl.is_terminal(before.status):
            return
        for field in ("occurrence_count", "first_seen_at", "last_seen_at"):
            if self.get(field) != before.get(field):
                frappe.throw(
                    _("Case {0} is terminal; evidence field '{1}' is frozen "
                      "and cannot be modified.").format(self.name, field),
                    frappe.ValidationError)

    def _stamp_resolution(self):
        """Stamp resolver identity/time when terminal; clear when active."""
        if cl.is_terminal(self.status):
            if not self.resolved_at:
                self.resolved_at = frappe.utils.now_datetime()
            if not self.resolved_by:
                self.resolved_by = frappe.session.user
        else:
            self.resolved_at = None
            self.resolved_by = None

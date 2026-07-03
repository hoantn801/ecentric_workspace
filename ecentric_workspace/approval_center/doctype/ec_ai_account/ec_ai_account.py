# Copyright (c) 2026, eCentric and contributors
"""EC AI Account - single source of truth for a real company AI account and the
person accountable for it. No secrets stored here."""
import frappe
from frappe import _
from frappe.model.document import Document

from ecentric_workspace.approval_center.engine.user_rules import (
    normalize_email, require_active_system_user)


class ECAIAccount(Document):
    def validate(self):
        self.account_email = normalize_email(self.account_email)
        require_active_system_user(self.account_manager, "account_manager",
                                   allow_admin_for_sysmanager=True)
        self.account_key = "{0}::{1}".format(self.ai_tool, self.account_email)
        self._require_manager_change_reason()

    def _require_manager_change_reason(self):
        if self.is_new():
            return
        before = self.get_doc_before_save()
        if before and before.account_manager and before.account_manager != self.account_manager:
            if not (self.manager_change_reason or "").strip():
                frappe.throw(_("A reason is required to change the account manager."))

    def on_update(self):
        before = self.get_doc_before_save()
        if before and before.account_manager and before.account_manager != self.account_manager:
            self.add_comment("Info", _("Account manager changed from {0} to {1}. Reason: {2}").format(
                before.account_manager, self.account_manager, self.manager_change_reason or ""))

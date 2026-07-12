# Copyright (c) 2026, eCentric and contributors
"""Append-only esign audit event (mirrors the EC Approval Action immutability pattern).

Hardened for remote review (2026-07-12):
  * DocPerm grants System Manager read/report/export/print ONLY - no role holds
    create/write/delete/share/email;
  * direct inserts are blocked for EVERY caller including Administrator and
    ignore_permissions (before_insert gate) - events may only be appended through
    the governed internal service (esign.events.emit), which validates upstream
    permissions and sanitizes metadata before setting the in-process append flag;
  * updates and deletes throw for every role (defense in depth)."""
import frappe
from frappe import _
from frappe.model.document import Document

APPEND_FLAG = "ec_esign_event_append"


class ECDigitalSignatureEvent(Document):
    def before_insert(self):
        if not getattr(frappe.flags, APPEND_FLAG, False):
            frappe.throw(_("EC Digital Signature Event is append-only via the governed "
                           "event service; direct inserts are not permitted."),
                         frappe.PermissionError)

    def validate(self):
        if not self.is_new():
            frappe.throw(_("EC Digital Signature Event is append-only; existing events cannot be edited."))

    def on_trash(self):
        frappe.throw(_("EC Digital Signature Event is append-only; events cannot be deleted."))

# Copyright (c) 2026, eCentric and contributors
"""EC Digital Signature Event is append-only for every role (controller-enforced,
mirroring EC Approval Action). Also: event metadata is sanitized at write time.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_events_immutable
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import events


class TestEsignEventsImmutable(FrappeTestCase):
    def test_update_and_delete_throw_even_as_administrator(self):
        frappe.set_user("Administrator")
        ev = frappe.get_doc({"doctype": "EC Digital Signature Event",
                             "event_type": "Created",
                             "event_time": frappe.utils.now_datetime(),
                             "erp_actor": "Administrator"}).insert(ignore_permissions=True)
        doc = frappe.get_doc("EC Digital Signature Event", ev.name)
        doc.error_summary = "tampered"
        with self.assertRaises(Exception):
            doc.save(ignore_permissions=True)
        with self.assertRaises(Exception):
            frappe.delete_doc("EC Digital Signature Event", ev.name,
                              ignore_permissions=True, force=True)

    def test_emit_sanitizes_metadata(self):
        frappe.set_user("Administrator")
        events.emit("Created", request_meta={"password": "supersecret",
                                             "PdfBase64": "AAAA", "ok": "yes"})
        row = frappe.get_all("EC Digital Signature Event",
                             filters={"event_type": "Created"},
                             fields=["name", "request_meta"],
                             order_by="creation desc", limit_page_length=1)[0]
        self.assertNotIn("supersecret", row.request_meta or "")
        self.assertNotIn("AAAA", row.request_meta or "")
        self.assertIn("redacted", row.request_meta or "")

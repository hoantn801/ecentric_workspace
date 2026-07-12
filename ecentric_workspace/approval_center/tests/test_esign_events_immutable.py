# Copyright (c) 2026, eCentric and contributors
"""EC Digital Signature Event: append-only via the GOVERNED service only
(remote-review hardening, 2026-07-12).

Model: DocPerm = System Manager read/report/export/print ONLY; direct create is
blocked for EVERY caller (System Manager, Administrator, even ignore_permissions)
by the controller's governed-append gate; update/delete/share blocked; the internal
event service still appends after upstream permission validation; metadata is
sanitized at write time.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_events_immutable
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import events
from ecentric_workspace.approval_center.tests import erp_fixtures as erp

EV = "EC Digital Signature Event"


def _direct_doc():
    return frappe.get_doc({"doctype": EV, "event_type": "Created",
                           "event_time": frappe.utils.now_datetime(),
                           "erp_actor": "Administrator"})


class TestEsignEventsImmutable(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_docperm_read_only_shape(self):
        perms = frappe.get_meta(EV).permissions
        self.assertEqual([p.role for p in perms], ["System Manager"])
        p = perms[0]
        self.assertEqual((p.read, p.report, p.export, p.get("print")), (1, 1, 1, 1))
        for right in ("create", "write", "delete", "share", "email"):
            self.assertFalse(p.get(right), "unexpected %s right on audit events" % right)

    def test_administrator_direct_insert_blocked_even_ignore_permissions(self):
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            _direct_doc().insert()
        with self.assertRaises(frappe.PermissionError):
            _direct_doc().insert(ignore_permissions=True)  # controller gate, not DocPerm

    def test_system_manager_direct_insert_blocked(self):
        sm_user = erp.make_user("zz_ev_sm@example.com", roles=("System Manager",))
        frappe.set_user(sm_user)
        with self.assertRaises(frappe.PermissionError):
            _direct_doc().insert()
        frappe.set_user("Administrator")

    def test_governed_internal_append_succeeds_and_flag_restored(self):
        frappe.set_user("Administrator")
        before = frappe.db.count(EV)
        events.emit("Created", request_meta={"ok": "yes"})
        self.assertEqual(frappe.db.count(EV), before + 1)
        self.assertFalse(getattr(frappe.flags, "ec_esign_event_append", False))

    def test_update_delete_share_blocked_after_creation(self):
        frappe.set_user("Administrator")
        events.emit("Created")
        name = frappe.get_all(EV, order_by="creation desc", limit_page_length=1,
                              pluck="name")[0]
        doc = frappe.get_doc(EV, name)
        doc.error_summary = "tampered"
        with self.assertRaises(Exception):
            doc.save(ignore_permissions=True)
        with self.assertRaises(Exception):
            frappe.delete_doc(EV, name, ignore_permissions=True, force=True)
        # share: no role holds share; a non-Administrator SM cannot share the event
        sm_user = erp.make_user("zz_ev_sm2@example.com", roles=("System Manager",))
        frappe.set_user(sm_user)
        with self.assertRaises(Exception):
            frappe.share.add_docshare(EV, name, "zz_ev_sm@example.com", read=1)
        frappe.set_user("Administrator")

    def test_emit_sanitizes_metadata(self):
        frappe.set_user("Administrator")
        events.emit("Created", request_meta={"password": "supersecret",
                                             "PdfBase64": "AAAA", "ok": "yes"})
        row = frappe.get_all(EV, filters={"event_type": "Created"},
                             fields=["request_meta"], order_by="creation desc",
                             limit_page_length=1)[0]
        self.assertNotIn("supersecret", row.request_meta or "")
        self.assertNotIn("AAAA", row.request_meta or "")
        self.assertIn("redacted", row.request_meta or "")

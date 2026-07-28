# Copyright (c) 2026, eCentric and contributors
"""Phase 1b.3.1b -- REAL FrappeTestCase coverage for native ToDo insert / update /
close behaviour and the fulfillment `date` + `ec_fulfillment` marker fields.

Runs on a bench (needs the Custom Field ToDo-ec_fulfillment from patch p044).
Proves in particular that an existing Open fulfillment ToDo with a missing/old
date is UPDATED in place to the governed fulfillment_due_at (not duplicated,
not skipped), and that close is scoped to marked fulfillment ToDos so an
unrelated Open ToDo on the same reference survives.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import service as engine

MARKER = engine.FULFILLMENT_MARKER   # "ec_fulfillment"


class TestToDoFulfillmentField(FrappeTestCase):
    def setUp(self):
        # A real, link-valid reference target (User always exists). The engine ToDo
        # helpers are reference-agnostic, so this exercises native ToDo storage.
        self.u = "1b31b-" + frappe.generate_hash(length=8) + "@test.local"
        if not frappe.db.exists("User", self.u):
            frappe.get_doc({"doctype": "User", "email": self.u, "first_name": "T131b",
                            "enabled": 1}).insert(ignore_permissions=True)
        self.dt = "User"
        self.ref = self.u
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for n in frappe.get_all("ToDo", {"reference_type": self.dt, "reference_name": self.ref},
                                pluck="name"):
            frappe.delete_doc("ToDo", n, force=True, ignore_permissions=True)
        frappe.delete_doc("User", self.u, force=True, ignore_permissions=True)

    def _opens(self):
        return frappe.get_all(
            "ToDo", {"reference_type": self.dt, "reference_name": self.ref, "status": "Open"},
            fields=["name", "allocated_to", "date", MARKER])

    def _marked_open(self):
        return frappe.get_all(
            "ToDo", {"reference_type": self.dt, "reference_name": self.ref, "status": "Open",
                     MARKER: 1}, fields=["name"])

    def test_custom_field_exists(self):
        # p044 must have created the marker Custom Field.
        self.assertTrue(frappe.db.exists("Custom Field", "ToDo-" + MARKER))

    def test_ensure_creates_marked_todo_with_date(self):
        engine._ensure_fulfillment_todo(self.dt, self.ref, "Administrator", "queue",
                                        date="2026-07-30 09:00:00")
        opens = self._opens()
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0].get(MARKER), 1)
        self.assertEqual(str(opens[0].date), "2026-07-30")

    def test_existing_open_todo_with_old_date_is_updated(self):
        # a native Open ToDo with an OLD date and NO marker (a legacy fulfillment task)
        td = frappe.get_doc({
            "doctype": "ToDo", "allocated_to": "Administrator",
            "reference_type": self.dt, "reference_name": self.ref,
            "date": "2000-01-01", "description": "legacy fulfillment"}).insert(ignore_permissions=True)
        engine._ensure_fulfillment_todo(self.dt, self.ref, "Administrator", "queue",
                                        date="2026-07-30 09:00:00")
        td.reload()
        self.assertEqual(str(td.date), "2026-07-30")     # UPDATED to fulfillment_due_at
        self.assertEqual(td.get(MARKER), 1)              # and MARKED
        self.assertEqual(len(self._opens()), 1)          # no duplicate created

    def test_existing_open_todo_with_missing_date_is_updated(self):
        td = frappe.get_doc({
            "doctype": "ToDo", "allocated_to": "Administrator",
            "reference_type": self.dt, "reference_name": self.ref,
            "description": "legacy no-date"}).insert(ignore_permissions=True)
        engine._ensure_fulfillment_todo(self.dt, self.ref, "Administrator", "queue",
                                        date="2026-07-30 09:00:00")
        td.reload()
        self.assertEqual(str(td.date), "2026-07-30")
        self.assertEqual(td.get(MARKER), 1)

    def test_close_fulfillment_is_scoped_to_marker(self):
        # marked fulfillment ToDo + an UNRELATED unmarked ToDo on the same reference
        engine._ensure_fulfillment_todo(self.dt, self.ref, "Administrator", "queue", "2026-07-30")
        unrel = frappe.get_doc({
            "doctype": "ToDo", "allocated_to": "Administrator",
            "reference_type": self.dt, "reference_name": self.ref,
            "description": "UNRELATED"}).insert(ignore_permissions=True)
        engine.close_fulfillment_todos(self.dt, self.ref)
        unrel.reload()
        self.assertEqual(unrel.status, "Open")           # unrelated survives
        self.assertEqual(self._marked_open(), [])        # marked closed

    def test_repeat_ensure_same_due_is_write_idempotent(self):
        # date-only comparison: re-running with the same governed due (even as a
        # datetime vs the stored Date) must NOT change ToDo.date -- true no-op.
        engine._ensure_fulfillment_todo(self.dt, self.ref, "Administrator", "queue",
                                        date="2026-07-30 09:00:00")
        opens = self._opens()
        self.assertEqual(len(opens), 1)
        first = frappe.db.get_value("ToDo", opens[0].name, "date")
        engine._ensure_fulfillment_todo(self.dt, self.ref, "Administrator", "queue",
                                        date="2026-07-30 23:59:00")   # same DATE, later time
        second = frappe.db.get_value("ToDo", opens[0].name, "date")
        self.assertEqual(str(first), str(second))    # unchanged (date-only match)
        self.assertEqual(len(self._opens()), 1)       # still exactly one

    def test_ensure_sole_todo_sm_not_in_pool_gets_exactly_one(self):
        engine.assign(self.dt, self.ref, ["Administrator"], "queue",
                      date="2026-07-30 09:00:00", fulfillment=True)
        # a System Manager claims (Administrator holds System Manager on a fresh bench)
        engine.ensure_sole_todo(self.dt, self.ref, "Administrator", "queue",
                                date="2026-07-30 09:00:00")
        opens = self._marked_open()
        self.assertEqual(len(opens), 1)                  # exactly one, not zero

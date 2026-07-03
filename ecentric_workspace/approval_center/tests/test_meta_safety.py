# Copyright (c) 2026, eCentric and contributors
"""Pre-migrate regression guard: Meta must build for every Approval Center
DocType, and no fieldname may shadow a Document/Meta member (which breaks
Meta.__init__ -> self.process(), e.g. a field literally named 'process').

  bench --site <site> run-tests --module \
    ecentric_workspace.approval_center.tests.test_meta_safety
"""
import frappe
from frappe.model.meta import Meta
from frappe.model.document import Document
from frappe.tests.utils import FrappeTestCase

DOCTYPES = [
    "EC Approval Process", "EC Approval Level", "EC Approval Participant",
    "EC Approval Request", "EC Approval Request Level", "EC Approval Request Approver",
    "EC Approval Action", "EC AI Tool", "EC AI Topup Request",
    "EC Approval Category", "EC Approval Type", "EC Approval Type Role",
    "EC Approval Type Department",
]


def _reserved_members():
    r = set()
    for cls in (Document, Meta):
        for n in dir(cls):
            if callable(getattr(cls, n, None)):
                r.add(n)
    try:
        r |= set(frappe.model.default_fields)
    except Exception:
        pass
    return r


class TestMetaSafety(FrappeTestCase):
    def test_meta_builds_for_all(self):
        for dt in DOCTYPES:
            self.assertTrue(frappe.get_meta(dt), "Meta failed for " + dt)

    def test_no_reserved_fieldnames(self):
        reserved = _reserved_members()
        for dt in DOCTYPES:
            for f in frappe.get_meta(dt).fields:
                self.assertNotIn(f.fieldname, reserved,
                                 "%s.%s shadows a reserved Document/Meta member" % (dt, f.fieldname))

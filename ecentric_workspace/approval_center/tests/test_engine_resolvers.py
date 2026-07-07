# Copyright (c) 2026, eCentric and contributors
"""Unit tests for the shared, reusable participant resolvers added for Batch 4:
Reference User Field, Reference Employee Manager, and the per-row fallback_user.
Generic (no form-specific hardcoding); exercised end-to-end again by the per-form tests.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_engine_resolvers
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import service as engine

PFX = "ZZRES_"


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _company():
    if not frappe.db.exists("Company", "ZZRES Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZRES Co", "abbr": "ZZRESC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZRES Co"


def _emp(user, reports_to=None):
    n = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not n:
        n = frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                            "company": _company(), "status": "Active", "gender": "Other",
                            "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
            ignore_permissions=True).name
    if reports_to:
        frappe.db.set_value("Employee", n, "reports_to", reports_to)
    return n


def _row(**kw):
    kw.setdefault("participant_purpose", "Approver")
    kw.setdefault("sort_order", 0)
    return frappe._dict(kw)


class TestEngineResolvers(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mgr = _user(PFX + "mgr@x.com")
        cls.rep = _user(PFX + "rep@x.com")
        cls.fb = _user(PFX + "fb@x.com")
        cls.mgr_emp = _emp(cls.mgr)
        cls.rep_emp = _emp(cls.rep, reports_to=cls.mgr_emp)

    def test_participant_meta_has_new_source_types(self):
        meta = frappe.get_meta("EC Approval Participant")
        opts = meta.get_field("source_type").options.split("\n")
        self.assertIn("Reference User Field", opts)
        self.assertIn("Reference Employee Manager", opts)
        self.assertTrue(meta.get_field("reference_field"))
        self.assertTrue(meta.get_field("fallback_user"))

    def test_reference_employee_manager(self):
        # manager of the employee named by an email field -> that employee's reports_to user
        self.assertEqual(engine._manager_user_of_employee(self.rep), self.mgr)
        self.assertIsNone(engine._manager_user_of_employee(self.mgr))          # top has no manager
        self.assertIsNone(engine._manager_user_of_employee("nobody@x.com"))    # unknown -> None

    def test_reference_user_field_resolves_from_context(self):
        # a User record's own "name" field holds a User id -> Reference User Field resolves it
        ctx = {"reference_doctype": "User", "reference_name": self.rep}
        out = engine.resolve_participants(
            [_row(source_type="Reference User Field", reference_field="name")], self.mgr, context=ctx)
        self.assertEqual([u for u, _l in out], [self.rep])

    def test_fallback_used_only_when_primary_empty(self):
        # requester has NO Employee/manager -> Requester Manager resolves nobody -> fallback used
        orphan = _user(PFX + "orphan@x.com")
        out = engine.resolve_participants(
            [_row(source_type="Requester Manager", fallback_user=self.fb)], orphan)
        self.assertEqual([u for u, _l in out], [self.fb])
        # requester WITH a manager -> primary resolves -> fallback NOT added
        out2 = engine.resolve_participants(
            [_row(source_type="Requester Manager", fallback_user=self.fb)], self.rep)
        self.assertEqual([u for u, _l in out2], [self.mgr])

    def test_no_fallback_no_resolution_is_failclosed(self):
        orphan = _user(PFX + "orphan2@x.com")
        out = engine.resolve_participants([_row(source_type="Requester Manager")], orphan)
        self.assertEqual(out, [])

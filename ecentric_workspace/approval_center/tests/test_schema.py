# Copyright (c) 2026, eCentric and contributors
"""B1 schema/controller tests for Approval Center.

Run on a Frappe site:
  bench --site <site> run-tests --module \
    ecentric_workspace.approval_center.tests.test_schema
"""
import frappe
from frappe.tests.utils import FrappeTestCase

CAT = "EC Approval Category"
TYP = "EC Approval Type"
_TEST_CAT = "ZZ_TEST_CAT"


def _mk_cat(code=_TEST_CAT, name="ZZ Test Category"):
    if frappe.db.exists(CAT, code):
        return frappe.get_doc(CAT, code)
    return frappe.get_doc({
        "doctype": CAT, "category_code": code, "category_name": name,
    }).insert(ignore_permissions=True)


def _mk_type(code, **kw):
    doc = frappe.get_doc({
        "doctype": TYP,
        "approval_code": code,
        "approval_title": kw.pop("approval_title", code.title()),
        "category": kw.pop("category", _TEST_CAT),
    })
    doc.update(kw)
    return doc


class TestApprovalCenterSchema(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _mk_cat()

    # S1
    def test_doctypes_exist_in_module(self):
        for dt in (CAT, TYP, "EC Approval Type Role", "EC Approval Type Department"):
            self.assertTrue(frappe.db.exists("DocType", dt), dt)
            self.assertEqual(frappe.get_meta(dt).module, "Approval Center")

    # S2 / S3
    def test_docname_equals_code(self):
        cat = _mk_cat("ZZ_CAT_NAME", "ZZ")
        self.assertEqual(cat.name, "ZZ_CAT_NAME")
        t = _mk_type("ZZ_CODE_NAME").insert(ignore_permissions=True)
        self.assertEqual(t.name, "ZZ_CODE_NAME")

    # S4
    def test_bad_category_link(self):
        with self.assertRaises(frappe.exceptions.LinkValidationError):
            _mk_type("ZZ_BAD_CAT", category="NOPE_DOES_NOT_EXIST").insert(ignore_permissions=True)

    # S5
    def test_duplicate_code(self):
        _mk_type("ZZ_DUP").insert(ignore_permissions=True)
        with self.assertRaises(frappe.exceptions.DuplicateEntryError):
            _mk_type("ZZ_DUP").insert(ignore_permissions=True)

    # S6
    def test_code_immutable(self):
        t = _mk_type("ZZ_IMMUT").insert(ignore_permissions=True)
        t.approval_code = "ZZ_IMMUT_CHANGED"
        with self.assertRaises(frappe.exceptions.ValidationError):
            t.save(ignore_permissions=True)

    # S7
    def test_code_regex(self):
        for bad in ("lower", "1STARTS_NUM", "HAS SPACE", "HAS-DASH", "X"):
            with self.assertRaises(frappe.exceptions.ValidationError, msg=bad):
                _mk_type(bad).insert(ignore_permissions=True)

    # S8
    def test_active_requires_route(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            _mk_type("ZZ_ACTIVE_NOROUTE", card_status="Active").insert(ignore_permissions=True)

    # S9
    def test_route_must_be_absolute(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            _mk_type("ZZ_ACTIVE_BADROUTE", card_status="Active",
                     route="approvals/x").insert(ignore_permissions=True)

    # S10
    def test_reserved_route_rejected(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            _mk_type("ZZ_RESERVED", card_status="Active",
                     route="/approval").insert(ignore_permissions=True)

    # S11
    def test_coming_soon_allows_empty_route(self):
        t = _mk_type("ZZ_CS_NOROUTE", card_status="Coming Soon").insert(ignore_permissions=True)
        self.assertEqual(t.route or "", "")

    # S12
    def test_defaults(self):
        t = _mk_type("ZZ_DEFAULTS").insert(ignore_permissions=True)
        self.assertEqual(t.card_status, "Coming Soon")
        self.assertEqual(t.process_status, "Discovery")
        self.assertEqual(t.visibility_mode, "All Internal Users")

    # S13
    def test_restricted_roles_empty_allowed(self):
        # empty restricted config is valid (fail-safe = no card later), not an error
        t = _mk_type("ZZ_RR_EMPTY", visibility_mode="Restricted Roles").insert(ignore_permissions=True)
        self.assertEqual(len(t.allowed_roles), 0)

    # S14
    def test_dedupe_children(self):
        t = _mk_type("ZZ_DEDUPE", visibility_mode="Restricted Roles")
        t.append("allowed_roles", {"role": "System Manager"})
        t.append("allowed_roles", {"role": "System Manager"})
        t.insert(ignore_permissions=True)
        self.assertEqual(len(t.allowed_roles), 1)

    # S15 (DocPerm: non System Manager cannot read)
    def test_docperm_system_manager_only(self):
        meta = frappe.get_meta(TYP)
        roles = {p.role for p in meta.permissions}
        self.assertEqual(roles, {"System Manager"})

# Copyright (c) 2026, eCentric and contributors
"""B2a tests: Approval Center catalog service + server-side visibility.

Run on a Frappe site:
  bench --site <site> run-tests --module \
    ecentric_workspace.approval_center.tests.test_catalog_api

Covers: Guest/Website-User denial, All Internal Users, Restricted Roles
allow/deny, Restricted Departments allow/deny + no cross-dept leak, empty
restriction hides card, Admin Only, Disabled visibility, inactive category,
deterministic sorting, and no invalid route exposed for Migrating/Coming Soon.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import catalog
from ecentric_workspace.approval_center import permissions as perms

CAT = "EC Approval Category"
TYP = "EC Approval Type"
PFX = "ZZB2A_"


def _cat(code, active=1, so=100):
    name = PFX + code
    if not frappe.db.exists(CAT, name):
        frappe.get_doc({"doctype": CAT, "category_code": name,
                        "category_name": name, "is_active": active,
                        "sort_order": so}).insert(ignore_permissions=True)
    return name


def _type(code, category, mode="All Internal Users", card="Coming Soon",
          route="", so=10, roles=None, depts=None):
    name = PFX + code
    if frappe.db.exists(TYP, name):
        frappe.delete_doc(TYP, name, ignore_permissions=True, force=True)
    doc = frappe.get_doc({
        "doctype": TYP, "approval_code": name, "approval_title": code.title(),
        "category": category, "visibility_mode": mode, "card_status": card,
        "route": route, "sort_order": so,
    })
    for r in (roles or []):
        doc.append("allowed_roles", {"role": r})
    for d in (depts or []):
        doc.append("allowed_departments", {"department": d})
    doc.insert(ignore_permissions=True)
    return name


def _user(email, roles=None, website=False):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "Website User" if website else "System User",
                            "send_welcome_email": 0, "enabled": 1})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
    u = frappe.get_doc("User", email)
    if roles and not website:
        u.add_roles(*roles)
    return email


def _codes(result):
    return {c["approval_code"] for c in result["types"]}


class TestApprovalCenterCatalog(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_guest_denied(self):
        frappe.set_user("Guest")
        res = catalog.list_catalog()
        self.assertEqual(res["types"], [])
        self.assertFalse(res["is_admin"])

    def test_website_user_denied(self):
        u = _user("zzb2a_web@example.com", website=True)
        _cat("C"); _type("PUB", PFX + "C", mode="All Internal Users")
        frappe.set_user(u)
        self.assertEqual(_codes(catalog.list_catalog()), set())

    def test_internal_sees_all_internal_users(self):
        cat = _cat("C"); t = _type("PUB", cat, mode="All Internal Users")
        u = _user("zzb2a_plain@example.com", roles=["Employee"])
        frappe.set_user(u)
        self.assertIn(t, _codes(catalog.list_catalog()))

    def test_restricted_roles_allow_and_deny(self):
        cat = _cat("C")
        t = _type("RR", cat, mode="Restricted Roles", roles=["Projects Manager"])
        allow = _user("zzb2a_pm@example.com", roles=["Projects Manager"])
        deny = _user("zzb2a_nopm@example.com", roles=["Employee"])
        frappe.set_user(allow); self.assertIn(t, _codes(catalog.list_catalog()))
        frappe.set_user(deny); self.assertNotIn(t, _codes(catalog.list_catalog()))

    def test_restricted_roles_empty_hides(self):
        cat = _cat("C"); t = _type("RRE", cat, mode="Restricted Roles", roles=[])
        u = _user("zzb2a_plain@example.com", roles=["Employee"])
        frappe.set_user(u); self.assertNotIn(t, _codes(catalog.list_catalog()))

    def test_restricted_departments_no_cross_leak(self):
        cat = _cat("C")
        da = _dept("ZZB2A Dept A"); db = _dept("ZZB2A Dept B")
        t = _type("RD", cat, mode="Restricted Departments", depts=[da])
        ua = _user("zzb2a_da@example.com", roles=["Employee"]); _emp(ua, da)
        ub = _user("zzb2a_db@example.com", roles=["Employee"]); _emp(ub, db)
        frappe.set_user(ua); self.assertIn(t, _codes(catalog.list_catalog()))
        frappe.set_user(ub); self.assertNotIn(t, _codes(catalog.list_catalog()))

    def test_restricted_departments_empty_hides(self):
        cat = _cat("C"); t = _type("RDE", cat, mode="Restricted Departments", depts=[])
        u = _user("zzb2a_plain@example.com", roles=["Employee"])
        frappe.set_user(u); self.assertNotIn(t, _codes(catalog.list_catalog()))

    def test_admin_only(self):
        cat = _cat("C"); t = _type("ADM", cat, mode="Admin Only")
        plain = _user("zzb2a_plain@example.com", roles=["Employee"])
        frappe.set_user(plain); self.assertNotIn(t, _codes(catalog.list_catalog()))
        frappe.set_user("Administrator"); self.assertIn(t, _codes(catalog.list_catalog()))

    def test_disabled_hidden_from_user_admin_optin(self):
        cat = _cat("C"); t = _type("DIS", cat, mode="All Internal Users", card="Disabled")
        plain = _user("zzb2a_plain@example.com", roles=["Employee"])
        frappe.set_user(plain); self.assertNotIn(t, _codes(catalog.list_catalog()))
        frappe.set_user("Administrator")
        self.assertNotIn(t, _codes(catalog.list_catalog()))                 # default: hidden
        self.assertIn(t, _codes(catalog.list_catalog(include_disabled_admin=1)))  # explicit opt-in

    def test_inactive_category_hidden_from_user(self):
        cat = _cat("INACTIVE", active=0)
        t = _type("INA", cat, mode="All Internal Users")
        plain = _user("zzb2a_plain@example.com", roles=["Employee"])
        frappe.set_user(plain); self.assertNotIn(t, _codes(catalog.list_catalog()))

    def test_no_invalid_route_for_non_active(self):
        cat = _cat("C")
        _type("CS", cat, card="Coming Soon", route="/approvals/should-not-leak")
        _type("MG", cat, card="Migrating", route="/approvals/should-not-leak")
        frappe.set_user("Administrator")
        for c in catalog.list_catalog()["types"]:
            if c["card_status"] in ("Coming Soon", "Migrating", "Disabled"):
                self.assertIsNone(c["route"], c["approval_code"])

    def test_deterministic_sorting(self):
        c1 = _cat("S1", so=10); c2 = _cat("S2", so=20)
        _type("B", c1, so=20); _type("A", c1, so=10); _type("Z", c2, so=10)
        frappe.set_user("Administrator")
        ours = [c["approval_code"] for c in catalog.list_catalog()["types"]
                if c["approval_code"].startswith(PFX) and c["category_code"] in (c1, c2)]
        # category sort_order then type sort_order then title
        self.assertEqual(ours[:3], [PFX + "A", PFX + "B", PFX + "Z"])


def _dept(name):
    if not frappe.db.exists("Department", {"department_name": name}):
        doc = frappe.get_doc({"doctype": "Department", "department_name": name})
        doc.insert(ignore_permissions=True)
        return doc.name
    return frappe.db.get_value("Department", {"department_name": name}, "name")


def _emp(user, department):
    ex = frappe.db.get_value("Employee", {"user_id": user})
    if ex:
        frappe.db.set_value("Employee", ex, "department", department)
        return ex
    doc = frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0],
                          "first_name": user.split("@")[0], "user_id": user,
                          "department": department, "status": "Active",
                          "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01",
                          "gender": "Other"})
    doc.insert(ignore_permissions=True)
    return doc.name

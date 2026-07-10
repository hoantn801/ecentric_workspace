# Copyright (c) 2026, eCentric and contributors
"""Governed department snapshot: population at submit + best-effort backfill leaves
unresolved rows blank (never guesses)."""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine.service import resolve_requester_department

PFX = "zzrepdept_"


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _dept(name):
    ex = frappe.db.get_value("Department", {"department_name": name}, "name")
    if ex:
        return ex
    return frappe.get_doc({"doctype": "Department", "department_name": name,
                           "company": frappe.defaults.get_global_default("company")}).insert(ignore_permissions=True).name


def _employee(user, department):
    n = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if n:
        frappe.db.set_value("Employee", n, "department", department)
        return n
    return frappe.get_doc({"doctype": "Employee", "first_name": user.split("@")[0], "user_id": user,
                           "company": frappe.defaults.get_global_default("company"),
                           "department": department, "status": "Active"}).insert(ignore_permissions=True).name


class TestReportingDepartment(FrappeTestCase):
    def test_resolver_prefers_employee_department(self):
        d = _dept("ZZ RepDept Alpha")
        u = _user(PFX + "alpha@x.com"); _employee(u, d)
        self.assertEqual(resolve_requester_department(u), d)

    def test_resolver_blank_when_no_governed_source(self):
        u = _user(PFX + "noemp@x.com")   # user with no Employee record
        self.assertIsNone(resolve_requester_department(u, None, None))

    def test_resolver_does_not_trust_missing_department(self):
        # business ref without a real department -> None (never guesses)
        u = _user(PFX + "noemp2@x.com")
        self.assertIsNone(resolve_requester_department(u, "EC Approval Type", "NONEXISTENT_TYPE_XYZ"))

    def test_backfill_fills_resolvable_leaves_rest_blank(self):
        d = _dept("ZZ RepDept Beta")
        u_ok = _user(PFX + "beta@x.com"); _employee(u_ok, d)
        u_blank = _user(PFX + "blank@x.com")   # no employee -> unresolvable
        # two requests with blank snapshot
        r_ok = frappe.get_doc({"doctype": "EC Approval Request", "approval_type": None,
                               "reference_doctype": "EC Approval Type", "reference_name": "X",
                               "requested_by": u_ok, "submitted_at": now_datetime(),
                               "approval_status": "Pending", "current_level": 1}).insert(ignore_permissions=True)
        r_blank = frappe.get_doc({"doctype": "EC Approval Request", "approval_type": None,
                                  "reference_doctype": "EC Approval Type", "reference_name": "X",
                                  "requested_by": u_blank, "submitted_at": now_datetime(),
                                  "approval_status": "Pending", "current_level": 1}).insert(ignore_permissions=True)
        frappe.db.set_value("EC Approval Request", r_ok.name, "requester_department", None, update_modified=False)
        frappe.db.set_value("EC Approval Request", r_blank.name, "requester_department", None, update_modified=False)
        frappe.db.commit()

        from ecentric_workspace.approval_center.patches import p040_backfill_requester_department as p040
        p040.execute()

        self.assertEqual(frappe.db.get_value("EC Approval Request", r_ok.name, "requester_department"), d)
        self.assertIn(frappe.db.get_value("EC Approval Request", r_blank.name, "requester_department"), (None, ""))

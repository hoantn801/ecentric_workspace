# Copyright (c) 2026, eCentric and contributors
"""Reporting scope-isolation tests (backend is the security boundary).

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_reporting_scope
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.reporting import scope as _scope
from ecentric_workspace.approval_center.reporting import service as _service

PFX = "zzrep_"
TYPE = "REP_TEST_TYPE"


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _dept(name):
    if not frappe.db.exists("Department", {"department_name": name}):
        d = frappe.get_doc({"doctype": "Department", "department_name": name,
                            "company": frappe.defaults.get_global_default("company")})
        d.insert(ignore_permissions=True)
        return d.name
    return frappe.db.get_value("Department", {"department_name": name}, "name")


def _employee(user, department=None):
    n = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if n:
        if department:
            frappe.db.set_value("Employee", n, "department", department)
        return n
    e = frappe.get_doc({"doctype": "Employee", "first_name": user.split("@")[0], "user_id": user,
                        "company": frappe.defaults.get_global_default("company"),
                        "department": department, "status": "Active"})
    e.insert(ignore_permissions=True)
    return e.name


def _ensure_type():
    if not frappe.db.exists("EC Approval Type", TYPE):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": TYPE,
                        "approval_title": "Reporting Test", "category": "OTHERS",
                        "card_status": "Coming Soon", "route": "approvals/rep-test"}).insert(ignore_permissions=True)


def _req(requester, department, status="Pending", approver=None, level=1):
    r = frappe.get_doc({
        "doctype": "EC Approval Request", "approval_type": TYPE,
        "reference_doctype": "EC Approval Type", "reference_name": TYPE,
        "requested_by": requester, "requester_department": department,
        "submitted_at": now_datetime(), "approval_status": status, "current_level": level,
    }).insert(ignore_permissions=True)
    frappe.get_doc({"doctype": "EC Approval Request Level", "approval_request": r.name,
                    "level_no": level, "level_name": "L%d" % level,
                    "level_status": "In Progress", "activated_at": now_datetime()}).insert(ignore_permissions=True)
    if approver:
        frappe.get_doc({"doctype": "EC Approval Request Approver", "approval_request": r.name,
                        "level_no": level, "approver": approver, "status": "Pending"}).insert(ignore_permissions=True)
    return r.name


class TestReportingScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_type()
        cls.d_fin = _dept("ZZ Reporting Finance")
        cls.d_hr = _dept("ZZ Reporting HR")
        cls.admin = _user(PFX + "admin@x.com"); frappe.get_doc("User", cls.admin).add_roles("System Manager")
        cls.mgr = _user(PFX + "mgr@x.com")
        cls.emp_mgr = _employee(cls.mgr, cls.d_fin)
        frappe.db.set_value("Department", cls.d_fin, "department_head", cls.emp_mgr)
        cls.req_fin = _user(PFX + "reqfin@x.com"); _employee(cls.req_fin, cls.d_fin)
        cls.req_hr = _user(PFX + "reqhr@x.com"); _employee(cls.req_hr, cls.d_hr)
        cls.approver = _user(PFX + "appr@x.com"); _employee(cls.approver, cls.d_hr)
        # requests
        cls.r_fin_own = _req(cls.req_fin, cls.d_fin, approver=cls.approver)
        cls.r_hr_own = _req(cls.req_hr, cls.d_hr)
        cls.r_mgr_own = _req(cls.mgr, cls.d_fin)
        frappe.db.commit()

    def _names(self, user):
        frappe.set_user(user)
        try:
            sc = _scope.resolve_scope(user)
            rows = _service.drilldown(sc, {"view": "open"}, limit=500)
        finally:
            frappe.set_user("Administrator")
        return {r["name"] for r in rows}, sc

    def test_admin_sees_all(self):
        names, sc = self._names(self.admin)
        self.assertEqual(sc["mode"], "admin")
        for n in (self.r_fin_own, self.r_hr_own, self.r_mgr_own):
            self.assertIn(n, names)

    def test_requester_sees_only_own(self):
        names, sc = self._names(self.req_hr)
        self.assertEqual(sc["mode"], "requester")
        self.assertIn(self.r_hr_own, names)
        self.assertNotIn(self.r_fin_own, names)
        self.assertNotIn(self.r_mgr_own, names)

    def test_approver_sees_assigned_plus_own(self):
        names, sc = self._names(self.approver)
        self.assertEqual(sc["mode"], "approver")
        self.assertIn(self.r_fin_own, names)      # assigned as approver
        self.assertNotIn(self.r_mgr_own, names)   # unrelated

    def test_department_manager_sees_dept_plus_own_no_leak(self):
        names, sc = self._names(self.mgr)
        self.assertEqual(sc["mode"], "department")
        self.assertIn(self.r_fin_own, names)      # dept member's request
        self.assertIn(self.r_mgr_own, names)      # own
        self.assertNotIn(self.r_hr_own, names)    # other dept -> NO leak

    def test_governance_role_name_alone_is_not_admin(self):
        u = _user(PFX + "fin_gov@x.com")
        # a plain governance-style role name must not grant org-wide scope
        self.assertNotEqual(_scope.resolve_scope(u)["mode"], "admin")

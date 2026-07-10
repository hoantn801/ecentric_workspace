# Copyright (c) 2026, eCentric and contributors
"""Kanban bottleneck-board dataset tests: same scope predicate as every other dashboard
dataset, grouping by level/approver, overdue-first sorting, card cap + true count.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_reporting_kanban
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, add_to_date

from ecentric_workspace.approval_center.reporting import scope as _scope
from ecentric_workspace.approval_center.reporting import service as _service

TYPE = "REP_KAN_TYPE"
PFX = "zzkan_"


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _ensure_type():
    if not frappe.db.exists("EC Approval Type", TYPE):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": TYPE, "approval_title": "Kanban Test",
                        "category": "OTHERS", "card_status": "Coming Soon", "route": "approvals/kan-test"}).insert(ignore_permissions=True)


def _req(requester, level, level_name, approver, activated, status="Pending"):
    r = frappe.get_doc({"doctype": "EC Approval Request", "approval_type": TYPE,
                        "reference_doctype": "EC Approval Type", "reference_name": TYPE,
                        "requested_by": requester, "requester_department": None,
                        "submitted_at": activated, "approval_status": status, "current_level": level}).insert(ignore_permissions=True)
    frappe.get_doc({"doctype": "EC Approval Request Level", "approval_request": r.name, "level_no": level,
                    "level_name": level_name, "level_status": "In Progress", "activated_at": activated}).insert(ignore_permissions=True)
    frappe.get_doc({"doctype": "EC Approval Request Approver", "approval_request": r.name, "level_no": level,
                    "approver": approver, "status": "Pending"}).insert(ignore_permissions=True)
    return r.name


class TestReportingKanban(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_type()
        now = now_datetime()
        cls.admin = _user(PFX + "admin@x.com"); frappe.get_doc("User", cls.admin).add_roles("System Manager")
        cls.reqA = _user(PFX + "reqA@x.com")
        cls.reqB = _user(PFX + "reqB@x.com")
        cls.appr1 = _user(PFX + "appr1@x.com")
        cls.appr2 = _user(PFX + "appr2@x.com")
        # L1: one very old (operational-default breached), one recent; L2: one recent
        cls.old = _req(cls.reqA, 1, "Finance review", cls.appr1, add_to_date(now, days=-10))
        cls.recent = _req(cls.reqB, 1, "Finance review", cls.appr1, add_to_date(now, hours=-1))
        cls.l2 = _req(cls.reqA, 2, "CEO review", cls.appr2, add_to_date(now, hours=-2))
        frappe.db.commit()

    def _kanban(self, user, filters=None):
        frappe.set_user(user)
        try:
            sc = _scope.resolve_scope(user)
            return _service.build_dashboard(sc, filters or {}).get("kanban", {}), sc
        finally:
            frappe.set_user("Administrator")

    def _admin_filters(self):
        from frappe.utils import get_first_day, get_last_day, nowdate
        return {"date_from": str(get_first_day(nowdate())) + " 00:00:00",
                "date_to": str(get_last_day(nowdate())) + " 23:59:59",
                "approval_type": TYPE}

    def test_group_by_level(self):
        kb, _ = self._kanban(self.admin, self._admin_filters())
        cols = {c["label"]: c for c in kb["by_level"]["columns"]}
        self.assertIn("Finance review", cols)
        self.assertIn("CEO review", cols)
        self.assertEqual(cols["Finance review"]["count"], 2)
        self.assertEqual(cols["CEO review"]["count"], 1)

    def test_overdue_and_sort(self):
        kb, _ = self._kanban(self.admin, self._admin_filters())
        fin = [c for c in kb["by_level"]["columns"] if c["label"] == "Finance review"][0]
        self.assertGreaterEqual(fin["overdue_count"], 1)             # the 10-day-old one breaches operational default
        self.assertEqual(fin["cards"][0]["request_name"], self.old)  # breached sorts first
        self.assertEqual(fin["cards"][0]["sla_state"], "breached")

    def test_group_by_approver(self):
        kb, _ = self._kanban(self.admin, self._admin_filters())
        cols = {c["key"]: c for c in kb["by_approver"]["columns"]}
        self.assertEqual(cols[self.appr1]["count"], 2)   # appr1 has the 2 L1 requests
        self.assertEqual(cols[self.appr2]["count"], 1)

    def test_card_shape(self):
        kb, _ = self._kanban(self.admin, self._admin_filters())
        card = kb["by_level"]["columns"][0]["cards"][0]
        for key in ("request_name", "title", "approval_type", "requester", "department",
                    "current_level", "pending_approvers", "pending_age_minutes", "sla_state",
                    "sla_source", "sla_remaining_minutes", "detail_route", "status"):
            self.assertIn(key, card)

    def test_scope_isolation_requester_sees_only_own(self):
        kb, sc = self._kanban(self.reqB, {"approval_type": TYPE})
        self.assertEqual(sc["mode"], "requester")
        names = set()
        for c in kb["by_level"]["columns"]:
            for card in c["cards"]:
                names.add(card["request_name"])
        self.assertIn(self.recent, names)       # own
        self.assertNotIn(self.old, names)        # reqA's
        self.assertNotIn(self.l2, names)         # reqA's

    def test_card_cap_and_true_count(self):
        # seed >20 at one fresh level for a fresh requester, assert cap=20 but count reflects all
        now = now_datetime()
        u = _user(PFX + "bulk@x.com"); frappe.get_doc("User", u).add_roles("System Manager")
        for i in range(23):
            _req(u, 5, "Bulk level", self.appr1, add_to_date(now, hours=-1))
        frappe.db.commit()
        kb, _ = self._kanban(u, {"approval_type": TYPE})
        bulk = [c for c in kb["by_level"]["columns"] if c["label"] == "Bulk level"]
        self.assertTrue(bulk)
        self.assertGreaterEqual(bulk[0]["count"], 23)
        self.assertLessEqual(len(bulk[0]["cards"]), 20)

# Copyright (c) 2026, eCentric and contributors
"""Reporting SLA-state tests (configured policy vs operational default vs unavailable)."""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, add_to_date

from ecentric_workspace.approval_center.reporting import sla as _sla


class TestReportingSla(FrappeTestCase):
    def test_configured_policy_breached(self):
        now = now_datetime()
        row = {"approval_status": "Pending", "due_at": add_to_date(now, hours=-1),
               "current_activated_at": add_to_date(now, hours=-5)}
        st = _sla.sla_state(row, ref_now=now)
        self.assertEqual(st["source"], "configured_policy")
        self.assertTrue(st["breached"])

    def test_configured_policy_not_breached(self):
        now = now_datetime()
        row = {"approval_status": "Pending", "due_at": add_to_date(now, hours=+5),
               "current_activated_at": add_to_date(now, hours=-1)}
        st = _sla.sla_state(row, ref_now=now)
        self.assertEqual(st["source"], "configured_policy")
        self.assertFalse(st["breached"])

    def test_operational_default_used_when_no_policy(self):
        now = now_datetime()
        row = {"approval_status": "Pending", "due_at": None,
               "current_activated_at": add_to_date(now, days=-20)}  # far past -> beyond 24 working hrs
        st = _sla.sla_state(row, ref_now=now)
        self.assertEqual(st["source"], "operational_default")
        self.assertTrue(st["breached"])

    def test_unavailable_when_no_due_and_no_activation(self):
        now = now_datetime()
        st = _sla.sla_state({"approval_status": "Pending", "due_at": None, "current_activated_at": None}, ref_now=now)
        self.assertEqual(st["source"], "unavailable")
        self.assertFalse(st["breached"])

    def test_closed_request_not_breached(self):
        now = now_datetime()
        row = {"approval_status": "Approved", "due_at": add_to_date(now, hours=-10),
               "current_activated_at": add_to_date(now, hours=-20)}
        st = _sla.sla_state(row, ref_now=now)
        self.assertFalse(st["breached"])
        self.assertFalse(st["applies"])

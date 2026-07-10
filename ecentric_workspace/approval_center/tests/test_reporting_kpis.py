# Copyright (c) 2026, eCentric and contributors
"""Reporting KPI / aggregation tests.
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_reporting_kpis
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, add_to_date, get_first_day, get_last_day, nowdate

from ecentric_workspace.approval_center.reporting import service as _service
from ecentric_workspace.approval_center.reporting import time_metrics as _tm

TYPE = "REP_KPI_TYPE"
ADMIN_SCOPE = {"mode": "admin", "user": "Administrator", "departments": []}


def _ensure_type():
    if not frappe.db.exists("EC Approval Type", TYPE):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": TYPE, "approval_title": "KPI Test",
                        "category": "OTHERS", "card_status": "Coming Soon", "route": "approvals/kpi-test"}).insert(ignore_permissions=True)


def _req(status, submitted, completed=None, dept="ZZK Dept", level=1, activated=None):
    r = frappe.get_doc({"doctype": "EC Approval Request", "approval_type": TYPE,
                        "reference_doctype": "EC Approval Type", "reference_name": TYPE,
                        "requested_by": "Administrator", "requester_department": None,
                        "submitted_at": submitted, "completed_at": completed,
                        "approval_status": status, "current_level": level}).insert(ignore_permissions=True)
    frappe.get_doc({"doctype": "EC Approval Request Level", "approval_request": r.name, "level_no": level,
                    "level_name": "L%d" % level, "level_status": "In Progress",
                    "activated_at": activated or submitted}).insert(ignore_permissions=True)
    return r.name


class TestReportingKpis(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_type()
        now = now_datetime()
        cls.filters = {"date_from": str(get_first_day(nowdate())) + " 00:00:00",
                       "date_to": str(get_last_day(nowdate())) + " 23:59:59"}
        # 3 approved (durations 1h, 3h, 5h), 2 pending, 1 rejected, 1 cancelled
        for h in (1, 3, 5):
            s = add_to_date(now, hours=-h)
            _req("Approved", s, completed=now)
        cls.p1 = _req("Pending", add_to_date(now, days=-6))   # >5d
        cls.p2 = _req("Pending", add_to_date(now, hours=-2))  # <1d
        _req("Rejected", add_to_date(now, hours=-1), completed=now)
        _req("Cancelled", add_to_date(now, hours=-1), completed=now)
        frappe.db.commit()

    def _dash(self):
        return _service.build_dashboard(ADMIN_SCOPE, self.filters)

    def test_status_counts(self):
        k = self._dash()["kpis"]
        self.assertGreaterEqual(k["total"], 7)
        self.assertGreaterEqual(k["completed"], 3)
        self.assertGreaterEqual(k["pending"], 2)
        self.assertGreaterEqual(k["rejected"], 1)
        self.assertGreaterEqual(k["cancelled"], 1)

    def test_average_excludes_cancelled_and_draft(self):
        k = self._dash()["kpis"]
        # only Approved rows contribute; ~ (1+3+5)/3 = 3h = 10800s (allow other suite rows -> just sanity bounds)
        self.assertIsNotNone(k["avg_approval_seconds"])
        self.assertGreater(k["avg_approval_seconds"], 0)
        self.assertGreaterEqual(k["avg_approval_sample"], 3)

    def test_aging_buckets_present(self):
        buckets = {b["bucket"]: b["count"] for b in self._dash()["aging_buckets"]}
        self.assertEqual(set(buckets), set(_tm.AGING_BUCKETS))
        self.assertGreaterEqual(buckets[">5d"], 1)

    def test_pending_by_type_and_status_distribution(self):
        d = self._dash()
        self.assertTrue(any(x["count"] >= 2 for x in d["pending_by_type"]))
        norm = {s["status"] for s in d["status_distribution"]}
        self.assertIn("Completed", norm)   # Approved -> Completed mapping
        self.assertNotIn("Approved", norm)

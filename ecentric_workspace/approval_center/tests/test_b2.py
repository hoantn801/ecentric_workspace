# Copyright (c) 2026, eCentric and contributors
"""Phase B2 tests: business calendar, business-hours calculator, SLA business
hours, and idempotent AI_TOPUP-V1 setup.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_b2
"""
from datetime import datetime, date

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import business_hours as bh
from ecentric_workspace.approval_center.ai_topup import setup as ai_setup

PFX = "ZZB2_"
_STD = ([{"weekday": d, "start_time": "09:00:00", "end_time": "12:00:00"} for d in
         ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]]
        + [{"weekday": d, "start_time": "13:00:00", "end_time": "18:00:00"} for d in
           ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]])


def _user(email, enabled=1, utype="System User"):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": utype, "enabled": enabled, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
    else:
        frappe.db.set_value("User", email, "enabled", enabled)
    return email


class TestBusinessHours(FrappeTestCase):
    def test_locked_examples(self):
        P = bh.build_periods(_STD)
        C = lambda dt, h, hol=None: bh.calculate_business_due_at(dt, h, P, hol or set())
        self.assertEqual(C(datetime(2026, 7, 6, 9, 0), 3), datetime(2026, 7, 6, 12, 0))
        self.assertEqual(C(datetime(2026, 7, 6, 11, 0), 3), datetime(2026, 7, 6, 15, 0))
        self.assertEqual(C(datetime(2026, 7, 6, 12, 30), 3), datetime(2026, 7, 6, 16, 0))
        self.assertEqual(C(datetime(2026, 7, 6, 17, 0), 3), datetime(2026, 7, 7, 11, 0))
        self.assertEqual(C(datetime(2026, 7, 10, 17, 0), 3), datetime(2026, 7, 13, 11, 0))
        self.assertEqual(C(datetime(2026, 7, 10, 17, 0), 3, {date(2026, 7, 13)}), datetime(2026, 7, 14, 11, 0))
        self.assertEqual(C(datetime(2026, 7, 11, 10, 0), 3), datetime(2026, 7, 13, 12, 0))
        self.assertEqual(C(datetime(2026, 7, 6, 12, 0), 3), datetime(2026, 7, 6, 16, 0))
        self.assertEqual(C(datetime(2026, 7, 6, 18, 0), 3), datetime(2026, 7, 7, 12, 0))

    def test_positive_duration(self):
        with self.assertRaises(ValueError):
            bh.calculate_business_due_at(datetime(2026, 7, 6, 9, 0), 0, bh.build_periods(_STD))


class TestBusinessCalendar(FrappeTestCase):
    def _cal(self, code, periods, active=1):
        c = frappe.get_doc({"doctype": "EC Approval Business Calendar", "calendar_code": PFX + code,
                            "calendar_name": code, "active": active})
        for p in periods:
            c.append("working_periods", p)
        return c

    def test_valid_split_day(self):
        self._cal("OK", _STD).insert(ignore_permissions=True)

    def test_overlap_rejected(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._cal("OV", [{"weekday": "Monday", "start_time": "09:00:00", "end_time": "12:00:00"},
                             {"weekday": "Monday", "start_time": "11:00:00", "end_time": "13:00:00"}]
                      ).insert(ignore_permissions=True)

    def test_duplicate_rejected(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._cal("DUP", [{"weekday": "Monday", "start_time": "09:00:00", "end_time": "12:00:00"},
                              {"weekday": "Monday", "start_time": "09:00:00", "end_time": "12:00:00"}]
                      ).insert(ignore_permissions=True)

    def test_invalid_times_rejected(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._cal("BAD", [{"weekday": "Monday", "start_time": "12:00:00", "end_time": "09:00:00"}]
                      ).insert(ignore_permissions=True)

    def test_empty_active_rejected(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._cal("EMPTY", [], active=1).insert(ignore_permissions=True)


class TestSLABusinessHours(FrappeTestCase):
    def test_requires_calendar(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            frappe.get_doc({"doctype": "EC Approval SLA Policy", "policy_code": PFX + "NOCAL",
                            "policy_name": "x", "duration_hours": 3, "use_business_hours": 1}
                           ).insert(ignore_permissions=True)

    def test_calendar_hours_still_work(self):
        p = frappe.get_doc({"doctype": "EC Approval SLA Policy", "policy_code": PFX + "CAL",
                            "policy_name": "x", "duration_hours": 5, "use_business_hours": 0}
                           ).insert(ignore_permissions=True)
        from ecentric_workspace.approval_center.engine import service as engine
        r = engine.resolve_sla(p.policy_code, frappe.utils.get_datetime("2026-07-06 09:00:00"))
        self.assertEqual(r["use_business_hours"], 0)
        self.assertTrue(r["due_at"])


class TestSetup(FrappeTestCase):
    def _users(self):
        return (["zzb2_op1@example.com", "zzb2_op2@example.com"],
                ["zzb2_op1@example.com", "zzb2_op2@example.com"],
                ["zzb2_fin1@example.com", "zzb2_fin2@example.com"])
    def _mkusers(self, *groups):
        for g in groups:
            for u in g:
                _user(u)

    def test_dry_run_makes_no_writes(self):
        op, ff, fin = self._users(); self._mkusers(op, ff, fin)
        before = frappe.db.exists("EC Approval Process", "AI_TOPUP-V1")
        rep = ai_setup.setup_ai_topup_v1(op, ff, fin, dry_run=1, apply=0)
        self.assertTrue(rep["result"].startswith("DRY_RUN_OK"))
        self.assertEqual(frappe.db.exists("EC Approval Process", "AI_TOPUP-V1"), before)

    def test_apply_idempotent_and_draft(self):
        op, ff, fin = self._users(); self._mkusers(op, ff, fin)
        ai_setup.setup_ai_topup_v1(op, ff, fin, dry_run=0, apply=1)
        ai_setup.setup_ai_topup_v1(op, ff, fin, dry_run=0, apply=1)  # idempotent re-run
        self.assertEqual(frappe.db.get_value("EC Approval Process", "AI_TOPUP-V1", "status"), "Draft")
        l2 = frappe.get_all("EC Approval Level",
                            filters={"approval_process": "AI_TOPUP-V1", "level_no": 2}, pluck="name")[0]
        approvers = frappe.get_all("EC Approval Participant",
                                   filters={"parent": l2, "participant_purpose": "Approver"}, pluck="user")
        self.assertEqual(sorted(approvers), sorted(op))  # no duplicates on re-run
        # Operation Approver (level) and Fulfiller (process) are separate rows/purposes
        ful = frappe.get_all("EC Approval Participant",
                             filters={"parent": "AI_TOPUP-V1", "parenttype": "EC Approval Process",
                                      "participant_purpose": "Fulfiller"}, pluck="user")
        self.assertEqual(sorted(ful), sorted(ff))
        # card remains inactive
        self.assertNotEqual(frappe.db.get_value("EC Approval Type", "AI_TOPUP", "card_status"), "Active")

    def test_disabled_user_rejected(self):
        _user("zzb2_dis@example.com", enabled=0)
        rep = ai_setup.setup_ai_topup_v1(["zzb2_dis@example.com"], ["zzb2_op1@example.com"],
                                         ["zzb2_fin1@example.com"], dry_run=1, apply=0)
        self.assertEqual(rep["result"], "BLOCKED")

    def test_website_user_rejected(self):
        _user("zzb2_web@example.com", utype="Website User")
        rep = ai_setup.setup_ai_topup_v1(["zzb2_web@example.com"], ["zzb2_op1@example.com"],
                                         ["zzb2_fin1@example.com"], dry_run=1, apply=0)
        self.assertEqual(rep["result"], "BLOCKED")

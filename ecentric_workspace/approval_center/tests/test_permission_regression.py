# Copyright (c) 2026, eCentric and contributors
"""Real-user approval permission regression (shared Approval Engine).

Reproduces the live bug: when a REAL approver (a plain Employee, no generic Frappe Share permission on the
business DocType) advances a request, engine.assign used to share the business doc under that user's session
-> PermissionError: No permission to share <BIZ> <name>. The engine now performs the share/ToDo grant as an
engine-owned internal op (ignore_permissions) AFTER the actor is authorized; the audit actor stays the real
user. All approve/reject actions below run as the real configured approver via frappe.set_user (never Admin);
Admin is used only for fixtures.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_permission_regression
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import hr_activity as hr_api
from ecentric_workspace.approval_center.api import system_request as sr_api
from ecentric_workspace.approval_center.api import livestream_sample as lv_api
from ecentric_workspace.approval_center.hr_activity import setup as hr_setup
from ecentric_workspace.approval_center.system_request import setup as sr_setup
from ecentric_workspace.approval_center.livestream_sample import setup as lv_setup

PFX = "ZZPERM_"


def _plain_user(email):
    """An active System User with ONLY the Employee role - deliberately NO Share permission on any
    Approval Center business DocType (matches the real approver whose action failed live)."""
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _company():
    if not frappe.db.exists("Company", "ZZPERM Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZPERM Co", "abbr": "ZZPRMC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZPERM Co"


def _employee(user):
    e = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if e:
        return e
    return frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                           "company": _company(), "status": "Active", "gender": "Other",
                           "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
        ignore_permissions=True).name


def _ensure_type(code, title):
    if not frappe.db.exists("EC Approval Type", code):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": code, "approval_title": title,
                        "card_status": "Coming Soon", "process_status": "Discovery"}).insert(ignore_permissions=True)


def _shared_with(biz, name, user):
    return bool(frappe.db.exists("DocShare", {"share_doctype": biz, "share_name": name, "user": user}))


def _open_todo(biz, name, user):
    return bool(frappe.db.exists("ToDo", {"reference_type": biz, "reference_name": name,
                                          "allocated_to": user, "status": "Open"}))


def _actions(ar, action):
    return frappe.get_all("EC Approval Action", filters={"approval_request": ar, "action": action}, pluck="actor")


class TestApprovalPermissionRegression(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, api, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    # ------------------------------------------------------------------ #
    # HR Activity - the reported form: 3 real approvers advance the request
    # ------------------------------------------------------------------ #
    def test_hr_activity_real_user_chain(self):
        hrm, hof, ceo = _plain_user(PFX + "hrm@x.com"), _plain_user(PFX + "hof@x.com"), _plain_user(PFX + "ceo@x.com")
        _ensure_type("HR_ACTIVITY", "HR Activity")
        hr_setup.setup_hr_activity_v1(hr_manager=[hrm], hof=[hof], ceo=[ceo], apply=1)
        frappe.db.set_value("EC Approval Process", "HR_ACTIVITY-V1", "status", "Active")
        req = _plain_user(PFX + "req@x.com"); _employee(req)
        outsider = _plain_user(PFX + "outsider@x.com")

        frappe.set_user(req)
        name = hr_api.save_draft(payload=frappe.as_json({
            "request_title": "T", "activity_type": "Company trip", "detail": "d", "start_date": "2026-09-01",
            "end_date": "2026-09-03", "participants": "all", "justification": "j", "estimated_budget": 100,
            "vendor_trainer_partner_info": "v", "request_attachment": "/f"}))["name"]
        hr_api.submit_request(name)
        frappe.set_user("Administrator")
        ar = self._ar(hr_api, name)
        self.assertTrue(_open_todo(hr_api.BIZ, name, hrm))       # first approver got a ToDo at submit

        # L1: HR Manager approves as the REAL user (no Share perm) - must not raise, and must advance
        frappe.set_user(hrm)
        hr_api.approve(name)                                     # <-- would raise "No permission to share" pre-fix
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)
        self.assertTrue(_shared_with(hr_api.BIZ, name, hof))     # next approver was granted access...
        self.assertTrue(_open_todo(hr_api.BIZ, name, hof))       # ...and a ToDo, by a non-share-perm actor

        # non-approver (outsider) cannot approve the current level
        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            hr_api.approve(name)
        frappe.set_user("Administrator")

        # L2 + L3 as real users
        frappe.set_user(hof); hr_api.approve(name)
        frappe.set_user(ceo); hr_api.approve(name)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        # each per-level approval action records the REAL approver as actor (the engine's final
        # "all levels approved" marker is legitimately Administrator - a system event, not a user action)
        approvers = _actions(ar, "Approved")
        self.assertIn(hrm, approvers); self.assertIn(hof, approvers); self.assertIn(ceo, approvers)
        self.assertEqual(frappe.db.get_value("EC Approval Action",
                         {"approval_request": ar, "level_no": 1, "action": "Approved"}, "actor"), hrm)

    # ------------------------------------------------------------------ #
    # System Request - fulfillment form: Operation reviewer approves (+ date), fulfiller completes
    # ------------------------------------------------------------------ #
    def test_system_request_real_user_flow(self):
        op = _plain_user(PFX + "op@x.com")
        _ensure_type("SYSTEM_REQUEST", "System Request")
        sr_setup.setup_system_request_v1(review_approvers=[op], fulfillers=[op], apply=1)
        frappe.db.set_value("EC Approval Process", "SYSTEM_REQUEST-V1", "status", "Active")
        req = _plain_user(PFX + "sreq@x.com"); _employee(req)

        frappe.set_user(req)
        name = sr_api.save_draft(payload=frappe.as_json({
            "request_title": "T", "request_type": "Access, permission", "description": "d", "priority": "High",
            "requester_expected_resolution_date": "2026-09-01"}))["name"]
        sr_api.submit_request(name)
        frappe.set_user("Administrator")
        ar = self._ar(sr_api, name)

        # Operation Review approve as the REAL operation user (no Share perm) + required date
        frappe.set_user(op)
        sr_api.approve(name, operation_expected_completion_date="2026-09-15")
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        self.assertEqual(frappe.db.get_value(sr_api.BIZ, name, "fulfillment_status"), "Assigned")
        self.assertEqual(str(frappe.db.get_value(sr_api.BIZ, name, "operation_expected_completion_date")), "2026-09-15")
        self.assertTrue(_open_todo(sr_api.BIZ, name, op))        # fulfiller got a ToDo (engine share, non-admin path)

        # fulfiller completes as the real user
        frappe.set_user(op)
        sr_api.claim_fulfillment(name)
        sr_api.complete_fulfillment(name, payload=frappe.as_json({"fulfillment_summary": "done"}))
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value(sr_api.BIZ, name, "fulfillment_status"), "Completed")
        self.assertIn(op, _actions(ar, "Approved"))             # audit actor is the real user

    # ------------------------------------------------------------------ #
    # Livestream Sample - single-level: real approver completes it
    # ------------------------------------------------------------------ #
    def test_livestream_real_user_single_level(self):
        sang = _plain_user(PFX + "sang@x.com")
        _ensure_type("LIVESTREAM_SAMPLE", "Livestream Sample Request")
        lv_setup.setup_livestream_sample_v1(reviewer=[sang], apply=1)
        frappe.db.set_value("EC Approval Process", "LIVESTREAM_SAMPLE-V1", "status", "Active")
        req = _plain_user(PFX + "lreq@x.com"); _employee(req)
        outsider = _plain_user(PFX + "loutsider@x.com")

        frappe.set_user(req)
        name = lv_api.save_draft(payload=frappe.as_json({
            "request_title": "T", "brand": "BrandX", "sample_detail": "SKU x5", "estimated_arrival_time": "2026-08-01"}))["name"]
        lv_api.submit_request(name)
        frappe.set_user("Administrator")
        ar = self._ar(lv_api, name)

        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            lv_api.approve(name)                                 # non-approver blocked
        frappe.set_user("Administrator")

        frappe.set_user(sang)
        lv_api.approve(name)                                     # real approver, single level -> Completed
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        self.assertIn(sang, _actions(ar, "Approved"))

# Copyright (c) 2026, eCentric and contributors
"""Outside Work (form #2) backend tests: submit/validation/manager, approval flow,
request-info + resubmit, ToDo lifecycle, timeline, admin override, no attendance update.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_outside_work
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import outside_work as api
from ecentric_workspace.approval_center.outside_work import setup as owsetup

PFX = "ZZOW_"


def _user(email, roles=("Employee",), enabled=1):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": enabled, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    name = "ZZOW Co"
    if not frappe.db.exists("Company", name):
        frappe.get_doc({"doctype": "Company", "company_name": name, "abbr": "ZZOWC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return name


def _employee(user, manager_emp=None):
    """Create an Employee for a user, optionally reporting to manager_emp."""
    existing = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if existing:
        return existing
    doc = frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                          "company": _company(), "status": "Active", "gender": "Other",
                          "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"})
    if manager_emp:
        doc.reports_to = manager_emp
    doc.insert(ignore_permissions=True)
    return doc.name


def _ensure_process():
    if not frappe.db.exists("EC Approval Type", "OUTSIDE_WORK"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "OUTSIDE_WORK",
                        "approval_title": "Outside Work", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    owsetup.setup_outside_work_v1(dry_run=0, apply=1)
    proc = frappe.db.get_value("EC Approval Process", {"process_code": "OUTSIDE_WORK-V1"}, "name")
    frappe.db.set_value("EC Approval Process", proc, "status", "Active")
    return proc


def _requester_with_manager():
    mgr = _user(PFX + "mgr@example.com")
    mgr_emp = _employee(mgr)
    req = _user(PFX + "req@example.com")
    _employee(req, manager_emp=mgr_emp)
    return req, mgr


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"request_title": "OW", "work_type": "Business trip", "start_date": "2026-08-01",
               "end_date": "2026-08-03", "duration_days": 3, "remarks": "team trip"}
    payload.update(over)
    res = api.save_draft(payload=frappe.as_json(payload))
    frappe.set_user("Administrator")
    return res["name"]


class TestOutsideWork(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def setUp(self):
        _ensure_process()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def _open_todos(self, name, user=None):
        f = {"reference_type": api.BIZ, "reference_name": name, "status": "Open"}
        if user:
            f["allocated_to"] = user
        return frappe.get_all("ToDo", filters=f, pluck="allocated_to")

    def test_save_draft_and_submit(self):
        req, mgr = _requester_with_manager()
        name = _draft(req)
        frappe.set_user(req)
        out = api.submit_request(name)
        self.assertTrue(out.get("submitted"))
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Pending")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        self.assertIn(mgr, self._open_todos(name))          # Direct Manager ToDo created

    def test_submit_blocked_when_no_direct_manager(self):
        u = _user(PFX + "nomgr@example.com")
        _employee(u)                                        # employee with no reports_to
        name = _draft(u)
        frappe.set_user(u)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(name)

    def test_submit_blocked_missing_required(self):
        req, mgr = _requester_with_manager()
        name = _draft(req, remarks="")                      # missing required remarks
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(name)

    def test_end_before_start_blocked(self):
        req, mgr = _requester_with_manager()
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.save_draft(payload=frappe.as_json({"request_title": "X", "work_type": "Other",
                "start_date": "2026-08-05", "end_date": "2026-08-01", "duration_days": 1, "remarks": "r"}))

    def test_duration_not_positive_blocked(self):
        req, mgr = _requester_with_manager()
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.save_draft(payload=frappe.as_json({"request_title": "X", "work_type": "Other",
                "start_date": "2026-08-01", "end_date": "2026-08-01", "duration_days": 0, "remarks": "r"}))

    def test_half_day_allowed(self):
        req, mgr = _requester_with_manager()
        name = _draft(req, duration_days=0.5, end_date="2026-08-01")
        self.assertEqual(float(frappe.db.get_value(api.BIZ, name, "duration_days")), 0.5)

    def test_manager_approve_completes(self):
        req, mgr = _requester_with_manager()
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name)
        frappe.set_user(mgr); api.approve(name)
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        self.assertEqual(self._open_todos(name), [])        # manager ToDo closed on completion

    def test_reject_requires_comment(self):
        req, mgr = _requester_with_manager()
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name)
        frappe.set_user(mgr)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.reject(name, comment="")
        api.reject(name, comment="không hợp lý")
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", self._ar(name), "approval_status"), "Rejected")

    def test_request_information_and_resubmit(self):
        req, mgr = _requester_with_manager()
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name)
        frappe.set_user(mgr)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.request_information(name, comment="")
        api.request_information(name, comment="bổ sung lịch trình")
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Information Required")
        # resubmit (non-material change) -> back to Pending at same level, no crash
        frappe.set_user(req)
        res = api.resubmit(name, payload=frappe.as_json({"remarks": "đã bổ sung lịch trình"}))
        self.assertFalse(res["restarted"])
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Pending")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "information_requested_from_level"), 0)
        self.assertIn(mgr, self._open_todos(name))          # manager ToDo recreated
        frappe.set_user(mgr); api.approve(name)             # approvable again
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")

    def test_admin_override(self):
        sm = _user(PFX + "sm@example.com", roles=("Employee", "System Manager"))
        req, mgr = _requester_with_manager()
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name)
        frappe.set_user(sm); api.admin_approve_current_level(name, reason="uat")
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        acts = frappe.get_all("EC Approval Action",
                              filters={"approval_request": ar, "action": "Approved", "actor": sm},
                              fields=["comment"])
        self.assertTrue(any("Admin override" in (x.comment or "") for x in acts))

    def test_timeline_records_actions(self):
        req, mgr = _requester_with_manager()
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name)
        frappe.set_user(mgr); api.approve(name)
        frappe.set_user("Administrator")
        acts = frappe.get_all("EC Approval Action", filters={"approval_request": self._ar(name)}, pluck="action")
        self.assertIn("Submitted", acts)
        self.assertIn("Approved", acts)

    def test_no_attendance_master_update(self):
        # v1 must not create/update any attendance master on completion
        req, mgr = _requester_with_manager()
        before = frappe.db.count("Attendance") if frappe.db.exists("DocType", "Attendance") else 0
        name = _draft(req)
        frappe.set_user(req); api.submit_request(name)
        frappe.set_user(mgr); api.approve(name)
        frappe.set_user("Administrator")
        after = frappe.db.count("Attendance") if frappe.db.exists("DocType", "Attendance") else 0
        self.assertEqual(before, after)


class TestOutsideWorkSetupActivation(FrappeTestCase):
    """setup/activation apply-argument behavior: apply=1 alone must apply; clear blockers when not ready."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ensure_type(self):
        if not frappe.db.exists("EC Approval Type", "OUTSIDE_WORK"):
            frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "OUTSIDE_WORK",
                            "approval_title": "Outside Work", "card_status": "Coming Soon",
                            "process_status": "Discovery"}).insert(ignore_permissions=True)

    def _retire(self):
        for p in frappe.get_all("EC Approval Process", filters={"process_code": "OUTSIDE_WORK-V1"}, pluck="name"):
            frappe.delete_doc("EC Approval Process", p, ignore_permissions=True, force=1)

    def test_setup_apply_only_applies(self):
        from ecentric_workspace.approval_center.outside_work import setup as owsetup
        self._ensure_type(); self._retire()
        r = owsetup.setup_outside_work_v1(apply=1)               # apply=1 alone, dry_run defaults to 1
        self.assertEqual(r["mode"], "apply")
        self.assertTrue(frappe.db.exists("EC Approval Process", {"process_code": "OUTSIDE_WORK-V1"}))

    def test_setup_dry_run_zero_apply_one_applies(self):
        from ecentric_workspace.approval_center.outside_work import setup as owsetup
        self._ensure_type(); self._retire()
        r = owsetup.setup_outside_work_v1(dry_run=0, apply=1)
        self.assertEqual(r["mode"], "apply")
        self.assertTrue(frappe.db.exists("EC Approval Process", {"process_code": "OUTSIDE_WORK-V1"}))

    def test_setup_default_is_dry_run(self):
        from ecentric_workspace.approval_center.outside_work import setup as owsetup
        self._ensure_type(); self._retire()
        r = owsetup.setup_outside_work_v1()                       # no args -> dry
        self.assertEqual(r["mode"], "dry_run")
        self.assertFalse(frappe.db.exists("EC Approval Process", {"process_code": "OUTSIDE_WORK-V1"}))

    def test_enable_uat_lists_blockers_when_not_ready(self):
        from ecentric_workspace.approval_center.outside_work import activation as owact
        sm = _user(PFX + "sm_act@example.com", roles=("Employee", "System Manager"))
        self._ensure_type(); self._retire()                      # process missing -> not ready
        frappe.set_user(sm)
        r = owact.enable_outside_work_uat(apply=1)
        frappe.set_user("Administrator")
        self.assertFalse(r["ready"])
        self.assertIn("process exists", r["blockers"])           # exact blocker surfaced

    def test_enable_uat_works_after_setup(self):
        from ecentric_workspace.approval_center.outside_work import setup as owsetup, activation as owact
        sm = _user(PFX + "sm_act2@example.com", roles=("Employee", "System Manager"))
        self._ensure_type(); self._retire()
        owsetup.setup_outside_work_v1(apply=1)                    # create process (Draft)
        frappe.set_user(sm)
        r = owact.enable_outside_work_uat(apply=1)
        frappe.set_user("Administrator")
        self.assertTrue(r["ready"])
        self.assertEqual(r["result"], "UAT_ENABLED")
        self.assertEqual(frappe.db.get_value("EC Approval Process",
                         {"process_code": "OUTSIDE_WORK-V1"}, "status"), "Active")


class TestOutsideWorkPageSync(FrappeTestCase):
    """Whitelisted, idempotent Web Page sync: created -> unchanged -> updated; SM-only."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_sync_created_unchanged_updated(self):
        if not frappe.db.exists("DocType", "Web Page"):
            self.skipTest("Web Page DocType not installed")
        from ecentric_workspace.approval_center.outside_work import page_sync
        # start clean
        for n in frappe.get_all("Web Page", filters={"route": page_sync.ROUTE}, pluck="name"):
            frappe.delete_doc("Web Page", n, ignore_permissions=True, force=1)
        r1 = page_sync.sync()
        self.assertEqual(r1["action"], "created")
        self.assertEqual(r1["route"], "approvals/outside-work")
        r2 = page_sync.sync()
        self.assertEqual(r2["action"], "unchanged")                 # idempotent, same source
        r3 = page_sync.sync(html="<div>changed</div>")
        self.assertEqual(r3["action"], "updated")

    def test_sync_endpoint_sm_only(self):
        u = _user(PFX + "psync_plain@example.com")                  # no System Manager
        from ecentric_workspace.approval_center.outside_work import page_sync
        frappe.set_user(u)
        with self.assertRaises(frappe.exceptions.PermissionError):
            page_sync.sync_outside_work_page()
        frappe.set_user("Administrator")

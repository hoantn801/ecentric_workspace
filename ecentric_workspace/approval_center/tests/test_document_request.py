# Copyright (c) 2026, eCentric and contributors
"""Document Request (form #4) backend tests: draft/submit, owner resolution via
Reference Department Head (Department.department_head), submit blocked when owner
unresolved, Owner->Operation->CEO approvals, fulfillment claim+complete, request-info
+resubmit, ToDo lifecycle, timeline, admin override, setup/activation apply, page_sync.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_document_request
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import document_request as api
from ecentric_workspace.approval_center.document_request import setup as drsetup
from ecentric_workspace.approval_center.document_request import activation as dract
from ecentric_workspace.approval_center.document_request import page_sync
from ecentric_workspace.approval_center.engine import service as engine

PFX = "ZZDOC_"
OP1 = PFX + "op1@example.com"
OP2 = PFX + "op2@example.com"
CEO = PFX + "ceo@example.com"


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _company():
    if not frappe.db.exists("Company", "ZZDOC Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZDOC Co", "abbr": "ZZDOCC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZDOC Co"


def _employee(user):
    e = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if e:
        return e
    return frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                           "company": _company(), "status": "Active", "gender": "Other",
                           "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
        ignore_permissions=True).name


def _department(name, head_user=None):
    dn = frappe.db.get_value("Department", {"department_name": name}, "name")
    if not dn:
        d = frappe.get_doc({"doctype": "Department", "department_name": name, "company": _company()})
        d.insert(ignore_permissions=True)
        dn = d.name
    if head_user:
        frappe.db.set_value("Department", dn, "department_head", _employee(head_user))
    return dn


def _has_mgr_email_field():
    return frappe.get_meta("Department").has_field("manager_email")


def _set_manager_email(dept, email):
    frappe.db.set_value("Department", dept, "manager_email", email)


def _disabled_user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": "dis",
                            "user_type": "System User", "enabled": 0, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
    else:
        frappe.db.set_value("User", email, "enabled", 0)
    return email


def _ensure_process():
    if not frappe.db.exists("EC Approval Type", "DOCUMENT_REQUEST"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "DOCUMENT_REQUEST",
                        "approval_title": "Document Request", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(OP1); _user(OP2); _user(CEO)
    drsetup.setup_document_request_v1(operation_reviewers=[OP1, OP2], ceo_reviewers=[CEO],
                                      fulfillers=[OP1, OP2], apply=1)
    frappe.db.set_value("EC Approval Process", "DOCUMENT_REQUEST-V1", "status", "Active")


def _requester():
    r = _user(PFX + "req@example.com")
    _employee(r)
    return r


def _owner_dept():
    owner = _user(PFX + "owner@example.com")
    return _department("ZZDOC Owner Dept", head_user=owner), owner


def _draft(user, owner_department, **over):
    frappe.set_user(user)
    payload = {"request_title": "DOC", "request_type": "Create", "document_name": "SOP",
               "owner_department": owner_department, "detail": "reason"}
    payload.update(over)
    res = api.save_draft(payload=frappe.as_json(payload))
    frappe.set_user("Administrator")
    return res["name"]


class TestDocumentRequest(FrappeTestCase):
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

    def _submit(self):
        dept, owner = _owner_dept()
        req = _requester()
        name = _draft(req, dept)
        frappe.set_user(req)
        api.submit_request(name)
        frappe.set_user("Administrator")
        return name, req, owner

    def test_submit_resolves_owner_as_level1(self):
        name, req, owner = self._submit()
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Pending")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 1)
        # L1 approver == owner department head (Reference Department Head)
        l1 = frappe.get_all("EC Approval Request Approver",
                            filters={"approval_request": ar, "level_no": 1}, pluck="approver")
        self.assertIn(owner, l1)
        self.assertIn(owner, self._open_todos(name))

    def test_submit_blocked_when_owner_unresolved(self):
        dept = _department("ZZDOC Headless Dept")            # no department_head, no manager_email
        if _has_mgr_email_field():
            _set_manager_email(dept, "")
        req = _requester()
        name = _draft(req, dept)
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError) as cm:
            api.submit_request(name)
        frappe.set_user("Administrator")
        self.assertFalse(self._ar(name))                     # not submitted
        self.assertIn("Không tìm thấy người phụ trách", str(cm.exception))  # VN diacritics

    def test_owner_resolves_via_manager_email(self):
        if not _has_mgr_email_field():
            self.skipTest("Department.manager_email field not installed")
        mgr = _user(PFX + "deptmgr@example.com")             # active System User, NOT an Employee head
        dept = _department("ZZDOC MgrEmail Dept")            # no department_head
        _set_manager_email(dept, mgr)
        req = _requester()
        name = _draft(req, dept)
        frappe.set_user(req)
        api.submit_request(name)
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Pending")
        l1 = frappe.get_all("EC Approval Request Approver",
                            filters={"approval_request": ar, "level_no": 1}, pluck="approver")
        self.assertIn(mgr, l1)                                # resolved via manager_email
        self.assertIn(mgr, self._open_todos(name))           # ToDo created for manager_email user

    def test_department_head_precedence_over_manager_email(self):
        if not _has_mgr_email_field():
            self.skipTest("Department.manager_email field not installed")
        head = _user(PFX + "headwins@example.com")
        other = _user(PFX + "mgremail2@example.com")
        dept = _department("ZZDOC BothSources Dept", head_user=head)   # has department_head
        _set_manager_email(dept, other)                       # also has manager_email
        self.assertEqual(engine.resolve_department_manager_user(dept), head)  # department_head wins

    def test_manager_email_inactive_user_blocks(self):
        if not _has_mgr_email_field():
            self.skipTest("Department.manager_email field not installed")
        dis = _disabled_user(PFX + "disabled@example.com")
        dept = _department("ZZDOC InactiveMgr Dept")          # no head
        _set_manager_email(dept, dis)
        self.assertIsNone(engine.resolve_department_manager_user(dept))  # inactive -> unresolved
        req = _requester()
        name = _draft(req, dept)
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(name)
        frappe.set_user("Administrator")

    def test_resolver_department_head_path_unchanged(self):
        owner = _user(PFX + "headonly@example.com")
        dept = _department("ZZDOC HeadOnly Dept", head_user=owner)
        self.assertEqual(engine.resolve_department_manager_user(dept), owner)  # backward compatible

    def test_full_chain_owner_operation_ceo_then_fulfillment(self):
        name, req, owner = self._submit()
        frappe.set_user(owner)
        api.approve(name)                                    # L1 Owner
        frappe.set_user(OP1)
        api.approve(name)                                    # L2 Operation (Any One)
        frappe.set_user(CEO)
        api.approve(name)                                    # L3 CEO -> final -> fulfillment
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "Assigned")
        self.assertTrue(self._open_todos(name))              # Operation fulfillment ToDos

    def test_fulfillment_claim_complete_summary_required(self):
        name, req, owner = self._submit()
        frappe.set_user(owner); api.approve(name)
        frappe.set_user(OP1); api.approve(name)
        frappe.set_user(CEO); api.approve(name)
        frappe.set_user(OP1); api.claim_fulfillment(name)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_owner"), OP1)
        frappe.set_user(OP1)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.complete_fulfillment(name, payload=frappe.as_json({"fulfillment_summary": ""}))
        api.complete_fulfillment(name, payload=frappe.as_json(
            {"fulfillment_summary": "done", "document_link": "https://x"}))
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "Completed")
        self.assertFalse(self._open_todos(name))

    def test_request_information_and_resubmit(self):
        name, req, owner = self._submit()
        frappe.set_user(owner)
        api.request_information(name, comment="cần thêm chi tiết")
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Information Required")
        self.assertFalse(self._open_todos(name))
        frappe.set_user(req)
        api.resubmit(name, payload=frappe.as_json({"detail": "chi tiết hơn"}))
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Pending")
        self.assertIn(owner, self._open_todos(name))

    def test_timeline_and_admin_override(self):
        name, req, owner = self._submit()
        frappe.set_user("Administrator")
        api.admin_approve_current_level(name, reason="urgent")   # override L1 only -> advances to L2
        ar = self._ar(name)
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)
        acts = frappe.get_all("EC Approval Action", filters={"approval_request": ar}, pluck="action")
        self.assertIn("Submitted", acts)
        self.assertIn("Approved", acts)

    def test_setup_dry_run_vs_apply_and_uat(self):
        rep = drsetup.setup_document_request_v1(operation_reviewers=[OP1], ceo_reviewers=[CEO],
                                                fulfillers=[OP1], dry_run=1, apply=0)
        self.assertEqual(rep["mode"], "dry_run")
        rep2 = drsetup.setup_document_request_v1(operation_reviewers=[OP1], ceo_reviewers=[CEO],
                                                 fulfillers=[OP1], apply=1)
        self.assertEqual(rep2["mode"], "apply")
        r = dract.enable_document_request_uat(apply=1)
        self.assertEqual(frappe.db.get_value("EC Approval Process", "DOCUMENT_REQUEST-V1", "status"), "Active")
        self.assertEqual(frappe.db.get_value("EC Approval Type", "DOCUMENT_REQUEST", "card_status"), "Coming Soon")
        self.assertEqual(r.get("result"), "UAT_ENABLED")

    def test_page_sync_created_unchanged_updated(self):
        if not frappe.db.exists("DocType", "Web Page"):
            self.skipTest("Web Page DocType not installed")
        for n in frappe.get_all("Web Page", filters={"route": page_sync.ROUTE}, pluck="name"):
            frappe.delete_doc("Web Page", n, ignore_permissions=True, force=1)
        self.assertEqual(page_sync.sync()["action"], "created")
        self.assertEqual(page_sync.sync()["action"], "unchanged")
        self.assertEqual(page_sync.sync(html="<div>x</div>")["action"], "updated")

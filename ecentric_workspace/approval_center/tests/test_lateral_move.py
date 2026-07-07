# Copyright (c) 2026, eCentric and contributors
"""Employee Lateral Move (Batch 4) backend tests - REAL-USER simulation via frappe.set_user.
Chain: requester -> Current Direct Manager -> New Line Manager (from new_line_manager field) ->
HR -> CEO -> Completed. Also: non-approver blocked, next approver gets ToDo + DocShare, audit actor
is the real user, block when current manager unresolved, block when new_line_manager is not an
active System User (proves the Reference User Field resolver drives L2).

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_lateral_move
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import lateral_move as api
from ecentric_workspace.approval_center.lateral_move import setup as lsetup

PFX = "ZZLM_"
HR = PFX + "hr@example.com"         # stands in for tuan.ly
CEO = PFX + "ceo@example.com"       # stands in for lam.nguyen


def _user(email, roles=("Employee",)):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    if not frappe.db.exists("Company", "ZZLM Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZLM Co", "abbr": "ZZLMC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZLM Co"


def _employee(user, reports_to=None):
    n = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not n:
        n = frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                            "company": _company(), "status": "Active", "gender": "Other",
                            "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
            ignore_permissions=True).name
    if reports_to:
        frappe.db.set_value("Employee", n, "reports_to", reports_to)
    return n


def _shared_with(name, user):
    return bool(frappe.db.exists("DocShare", {"share_doctype": api.BIZ, "share_name": name, "user": user}))


def _open_todo(name, user):
    return bool(frappe.db.exists("ToDo", {"reference_type": api.BIZ, "reference_name": name,
                                          "allocated_to": user, "status": "Open"}))


def _actions(ar, action):
    return frappe.get_all("EC Approval Action", filters={"approval_request": ar, "action": action}, pluck="actor")


def _ensure_process():
    if not frappe.db.exists("EC Approval Type", "LATERAL_MOVE"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "LATERAL_MOVE",
                        "approval_title": "Employee Lateral Move", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(HR); _user(CEO)
    lsetup.setup_lateral_move_v1(hr=[HR], ceo=[CEO], apply=1)
    frappe.db.set_value("EC Approval Process", "LATERAL_MOVE-V1", "status", "Active")


def _draft(user, nlm, **over):
    frappe.set_user(user)
    payload = {"request_title": "Lateral - X", "new_position": "Analyst II", "new_department": "Service",
               "new_line_manager": nlm, "transfer_reason": "Growth.", "start_date": "2026-10-01"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestLateralMove(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        _ensure_process()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def test_full_chain_four_levels(self):
        mgr = _user(PFX + "mgr@example.com")
        nlm = _user(PFX + "nlm@example.com")      # new line manager (active system user)
        req = _user(PFX + "req@example.com")
        _employee(req, reports_to=_employee(mgr))
        _employee(nlm)
        outsider = _user(PFX + "outsider@example.com")

        name = _draft(req, nlm)
        frappe.set_user(req)
        api.submit_request(name)
        frappe.set_user("Administrator")
        ar = self._ar(name)
        self.assertTrue(_shared_with(name, mgr) and _open_todo(name, mgr))   # current manager assigned

        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name, comment="x")
        frappe.set_user("Administrator")

        frappe.set_user(mgr); api.approve(name, comment="cur mgr"); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)
        # L2 approver resolved from new_line_manager field via Reference User Field
        self.assertTrue(_shared_with(name, nlm) and _open_todo(name, nlm))
        frappe.set_user(nlm); api.approve(name, comment="new mgr"); frappe.set_user("Administrator")
        frappe.set_user(HR); api.approve(name, comment="hr"); frappe.set_user("Administrator")
        frappe.set_user(CEO); api.approve(name, comment="ceo"); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        approvers = _actions(ar, "Approved")
        for u in (mgr, nlm, HR, CEO):
            self.assertIn(u, approvers)
        self.assertEqual(frappe.db.get_value("EC Approval Action",
                         {"approval_request": ar, "level_no": 2, "action": "Approved"}, "actor"), nlm)

    def test_block_when_no_current_manager(self):
        nlm = _user(PFX + "nlm2@example.com"); _employee(nlm)
        orphan = _user(PFX + "orphan@example.com"); _employee(orphan)   # no reports_to
        name = _draft(orphan, nlm)
        frappe.set_user(orphan)
        with self.assertRaises(Exception):
            api.submit_request(name)
        frappe.set_user("Administrator")
        self.assertFalse(frappe.db.get_value(api.BIZ, name, "approval_request"))

    def test_block_when_new_line_manager_not_active_user(self):
        mgr = _user(PFX + "mgr3@example.com")
        req = _user(PFX + "req3@example.com"); _employee(req, reports_to=_employee(mgr))
        name = _draft(req, "ghost@nowhere.com")   # valid email, but not a system user
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(name)
        frappe.set_user("Administrator")
        self.assertFalse(frappe.db.get_value(api.BIZ, name, "approval_request"))

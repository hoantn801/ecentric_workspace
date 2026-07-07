# Copyright (c) 2026, eCentric and contributors
"""Asset Damage or Loss (Batch 5) backend tests - REAL-USER simulation via frappe.set_user.
Proves the shared engine's ANY_ONE level: L1 Operation Review has two approvers; either one advances
the request to CEO, and the other can no longer act on the (now advanced) level. Then CEO completes.
Also: non-Operation user blocked, next approver gets ToDo + DocShare, audit actor is the real user,
conditional 'Other' + multi-select + required-attachment validation.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_asset_damage_loss
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import asset_damage_loss as api
from ecentric_workspace.approval_center.asset_damage_loss import setup as asetup

PFX = "ZZADL_"
OP1 = PFX + "op1@example.com"      # stands in for hoan.tran
OP2 = PFX + "op2@example.com"      # stands in for thuong.nguyen
CEO = PFX + "ceo@example.com"      # stands in for lam.nguyen


def _user(email, roles=("Employee",)):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def _company():
    if not frappe.db.exists("Company", "ZZADL Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZADL Co", "abbr": "ZZADLC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZADL Co"


def _employee(user):
    n = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not n:
        n = frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                            "company": _company(), "status": "Active", "gender": "Other",
                            "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
            ignore_permissions=True).name
    return n


def _shared_with(name, user):
    return bool(frappe.db.exists("DocShare", {"share_doctype": api.BIZ, "share_name": name, "user": user}))


def _open_todo(name, user):
    return bool(frappe.db.exists("ToDo", {"reference_type": api.BIZ, "reference_name": name,
                                          "allocated_to": user, "status": "Open"}))


def _actions(ar, action):
    return frappe.get_all("EC Approval Action", filters={"approval_request": ar, "action": action}, pluck="actor")


def _ensure_process():
    if not frappe.db.exists("EC Approval Type", "ASSET_DAMAGE_LOSS"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "ASSET_DAMAGE_LOSS",
                        "approval_title": "Asset Damage or Loss", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    _user(OP1); _user(OP2); _user(CEO)
    asetup.setup_asset_damage_loss_v1(operation_reviewers=[OP1, OP2], ceo=[CEO], apply=1)
    frappe.db.set_value("EC Approval Process", "ASSET_DAMAGE_LOSS-V1", "status", "Active")


def _draft(user, **over):
    frappe.set_user(user)
    payload = {"request_title": "Broken laptop", "asset_type": "Laptop", "asset_code": "LAP-001",
               "incident_type": "Damage", "incident_description": "Dropped it.", "incident_date": "2026-07-01",
               "incident_location": "HCM office", "physical_damage": "Cracked screen",
               "data_compromised": "None - Internal", "impact_on_operations": "Cannot work for 2 days",
               "estimated_repair_cost": 2000000, "estimated_value_lost_stolen_asset": 0,
               "recommended_actions": "Repair", "request_attachment": "/private/files/photo.jpg"}
    payload.update(over)
    name = api.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


class TestAssetDamageLoss(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))
        _ensure_process()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def test_any_one_operation_then_ceo(self):
        req = _user(PFX + "req@example.com"); _employee(req)
        outsider = _user(PFX + "outsider@example.com")

        name = _draft(req)
        frappe.set_user(req); api.submit_request(name); frappe.set_user("Administrator")
        ar = self._ar(name)
        # BOTH operation reviewers are snapshotted at L1 and both hold the ToDo/DocShare
        approvers_l1 = frappe.get_all("EC Approval Request Approver",
                                      filters={"approval_request": ar, "level_no": 1}, pluck="approver")
        self.assertEqual(set(approvers_l1), {OP1, OP2})
        self.assertTrue(_open_todo(name, OP1) and _open_todo(name, OP2))

        # a non-Operation user cannot approve L1
        frappe.set_user(outsider)
        with self.assertRaises(Exception):
            api.approve(name, comment="x")
        frappe.set_user("Administrator")

        # ONE operation reviewer approves -> advances to CEO (Any One)
        frappe.set_user(OP1); api.approve(name, comment="ops ok"); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)
        self.assertTrue(_shared_with(name, CEO) and _open_todo(name, CEO))

        # the OTHER operation reviewer can no longer act on the advanced level
        frappe.set_user(OP2)
        with self.assertRaises(Exception):
            api.approve(name, comment="late")
        frappe.set_user("Administrator")

        # CEO approves -> Completed
        frappe.set_user(CEO); api.approve(name, comment="ceo ok"); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        approved = _actions(ar, "Approved")
        self.assertIn(OP1, approved); self.assertIn(CEO, approved)
        self.assertEqual(frappe.db.get_value("EC Approval Action",
                         {"approval_request": ar, "level_no": 1, "action": "Approved"}, "actor"), OP1)

    def test_conditional_and_multiselect_validation(self):
        req = _user(PFX + "vreq@example.com"); _employee(req)
        # asset_type Other without asset_type_other -> blocked
        n1 = _draft(req, asset_type="Other", asset_type_other="")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n1)
        frappe.set_user("Administrator")
        # recommended_actions with an invalid value -> blocked
        n2 = _draft(req, recommended_actions="Repair, Nonsense")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n2)
        frappe.set_user("Administrator")
        # recommended_actions includes Other but no other text -> blocked
        n3 = _draft(req, recommended_actions="Other", recommended_actions_other="")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(n3)
        frappe.set_user("Administrator")

    def test_required_attachment(self):
        req = _user(PFX + "areq@example.com"); _employee(req)
        name = _draft(req, request_attachment="")
        frappe.set_user(req)
        with self.assertRaises(Exception):
            api.submit_request(name)
        frappe.set_user("Administrator")

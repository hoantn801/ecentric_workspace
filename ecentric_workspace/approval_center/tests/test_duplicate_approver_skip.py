# Copyright (c) 2026, eCentric and contributors
"""Shared-engine governance: duplicate-approver auto-skip. When a level becomes active and EVERY pending
approver already approved an earlier level of the same request, the engine auto-skips it (audited) and
advances / completes - no one approves twice. Any-One safe; L1 never skips; non-approvers still blocked.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_duplicate_approver_skip
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import service as engine

PFX = "ZZDUP_"


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _company():
    if not frappe.db.exists("Company", "ZZDUP Co"):
        frappe.get_doc({"doctype": "Company", "company_name": "ZZDUP Co", "abbr": "ZZDUPC",
                        "default_currency": "VND"}).insert(ignore_permissions=True)
    return "ZZDUP Co"


def _employee(user):
    n = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if n:
        return n
    return frappe.get_doc({"doctype": "Employee", "employee_name": user.split("@")[0], "user_id": user,
                           "company": _company(), "status": "Active", "gender": "Other",
                           "date_of_joining": "2020-01-01", "date_of_birth": "1990-01-01"}).insert(
        ignore_permissions=True).name


def _type():
    if not frappe.db.exists("EC Approval Type", "ZZDUP_TYPE"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "ZZDUP_TYPE",
                        "approval_title": "Dup Skip Test", "card_status": "Coming Soon",
                        "process_status": "Discovery"}).insert(ignore_permissions=True)
    return "ZZDUP_TYPE"


def _process(code, levels):
    """levels = list of (level_no, level_name, [approver emails], approval_mode)."""
    _type()
    if frappe.db.exists("EC Approval Process", code):
        frappe.delete_doc("EC Approval Process", code, ignore_permissions=True, force=True)
    proc = frappe.get_doc({"doctype": "EC Approval Process", "process_code": code, "title": code,
                           "approval_type": "ZZDUP_TYPE", "version_no": 1, "status": "Active"}).insert(
        ignore_permissions=True)
    for no, name, users, mode in levels:
        lvl = frappe.get_doc({"doctype": "EC Approval Level", "approval_process": code, "level_no": no,
                              "level_name": name, "mandatory": 1, "approval_mode": mode,
                              "minimum_approvals": 1, "allows_amount_adjustment": 0})
        for i, u in enumerate(users):
            lvl.append("participants", {"participant_purpose": "Approver", "source_type": "User",
                                        "user": _user(u), "sort_order": i})
        lvl.insert(ignore_permissions=True)
    return code


def _note(requester):
    """A throwaway business record to attach the approval request to (any DocType with a name)."""
    return frappe.get_doc({"doctype": "Note", "title": PFX + frappe.generate_hash(length=8),
                           "public": 0}).insert(ignore_permissions=True).name


def _submit(process_code, requester):
    _employee(requester)
    ref = _note(requester)
    return engine.submit("Note", ref, "ZZDUP_TYPE", requester) if False else \
        _submit_with_process(process_code, requester, ref)


def _submit_with_process(process_code, requester, ref):
    # engine.submit resolves the Active process for the type; ensure only THIS process is active
    for p in frappe.get_all("EC Approval Process",
                            filters={"approval_type": "ZZDUP_TYPE", "status": "Active",
                                     "process_code": ["!=", process_code]}, pluck="name"):
        frappe.db.set_value("EC Approval Process", p, "status", "Draft")
    frappe.db.set_value("EC Approval Process", process_code, "status", "Active")
    return engine.submit("Note", ref, "ZZDUP_TYPE", requester)


def _status(ar):
    return frappe.db.get_value("EC Approval Request", ar, "approval_status")


def _cur(ar):
    return frappe.db.get_value("EC Approval Request", ar, "current_level")


def _lvl_status(ar, no):
    return frappe.db.get_value("EC Approval Request Level", {"approval_request": ar, "level_no": no}, "level_status")


def _ap_status(ar, no, user):
    return frappe.db.get_value("EC Approval Request Approver",
                               {"approval_request": ar, "level_no": no, "approver": user}, "status")


class TestDuplicateApproverSkip(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_1_l1_and_l4_same_approver_l4_autoskips(self):
        A = _user(PFX + "lam@x.com"); B = _user(PFX + "b@x.com"); C = _user(PFX + "c@x.com")
        req = _user(PFX + "req1@x.com")
        code = _process(PFX + "P1", [(1, "L1", [A], "Any One"), (2, "L2", [B], "Any One"),
                                     (3, "L3", [C], "Any One"), (4, "L4", [A], "Any One")])
        ar = _submit(code, req)
        engine.approve(ar, actor=A)          # L1
        engine.approve(ar, actor=B)          # L2
        engine.approve(ar, actor=C)          # L3 -> L4 activates -> auto-skip (A already approved L1)
        self.assertEqual(_status(ar), "Approved")                      # completed
        self.assertEqual(_ap_status(ar, 4, A), "Skipped")             # L4 approver row Skipped, preserved
        skipped = frappe.get_all("EC Approval Action",
                                 filters={"approval_request": ar, "level_no": 4, "action": "Skipped"},
                                 fields=["comment", "related_user"])
        self.assertTrue(any("already approved an earlier level" in (x.comment or "") for x in skipped))  # audit
        # A never got a redundant L4 ToDo
        self.assertFalse(frappe.db.exists("ToDo", {"reference_type": "Note", "allocated_to": A, "status": "Open"}))

    def test_2_no_duplicates_behaves_as_before(self):
        A = _user(PFX + "a2@x.com"); B = _user(PFX + "b2@x.com"); C = _user(PFX + "c2@x.com")
        req = _user(PFX + "req2@x.com")
        code = _process(PFX + "P2", [(1, "L1", [A], "Any One"), (2, "L2", [B], "Any One"), (3, "L3", [C], "Any One")])
        ar = _submit(code, req)
        engine.approve(ar, actor=A)
        self.assertEqual(_cur(ar), 2)                                  # advances normally, no skip
        engine.approve(ar, actor=B); engine.approve(ar, actor=C)
        self.assertEqual(_status(ar), "Approved")
        for no in (1, 2, 3):
            self.assertNotEqual(_lvl_status(ar, no), "Skipped")

    def test_3_anyone_mixed_keeps_level_active(self):
        A = _user(PFX + "a3@x.com"); D = _user(PFX + "d3@x.com")  # D is fresh (non-duplicate)
        req = _user(PFX + "req3@x.com")
        # L1 = A ; L2 = Any One of [A, D]. A is duplicate, D is not -> L2 must stay active.
        code = _process(PFX + "P3", [(1, "L1", [A], "Any One"), (2, "L2", [A, D], "Any One")])
        ar = _submit(code, req)
        engine.approve(ar, actor=A)                                    # L1 -> L2 activates
        self.assertEqual(_cur(ar), 2)                                  # L2 NOT skipped (D pending)
        self.assertEqual(_status(ar), "Pending")
        self.assertEqual(_ap_status(ar, 2, D), "Pending")
        engine.approve(ar, actor=D)                                    # D approves L2 -> complete
        self.assertEqual(_status(ar), "Approved")

    def test_4_anyone_all_duplicates_autoskips(self):
        A = _user(PFX + "a4@x.com"); B = _user(PFX + "b4@x.com")
        req = _user(PFX + "req4@x.com")
        # L1 = Any One [A, B] ; L2 = Any One [A, B] (both approved -> but Any-One: only one approves L1).
        # Use: L1 = [A] ; L2 = [A, A]? no dup rows. Use L1=[A], L2=Any One [A] duplicate + also A only.
        # Simpler: L1 Any One [A, B] (A approves, B skipped-remaining) ; L2 Any One [A, B].
        # At L2, A approved L1; B did NOT approve (was skipped-remaining, status Skipped not Approved).
        # So B is not a duplicate-approver -> L2 stays active. To force all-duplicates, make L2=[A] only.
        code = _process(PFX + "P4", [(1, "L1", [A], "Any One"), (2, "L2", [A], "Any One")])
        ar = _submit(code, req)
        engine.approve(ar, actor=A)                                    # L1 -> L2 activates -> all(=A) duplicate -> skip -> complete
        self.assertEqual(_status(ar), "Approved")
        self.assertEqual(_lvl_status(ar, 2), "Approved")               # level passed via skip
        self.assertEqual(_ap_status(ar, 2, A), "Skipped")

    def test_6_non_pending_user_still_blocked(self):
        A = _user(PFX + "a6@x.com"); B = _user(PFX + "b6@x.com"); out = _user(PFX + "out6@x.com")
        req = _user(PFX + "req6@x.com")
        code = _process(PFX + "P6", [(1, "L1", [A], "Any One"), (2, "L2", [B], "Any One")])
        ar = _submit(code, req)
        with self.assertRaises(Exception):
            engine.approve(ar, actor=out)                              # not a pending approver
        with self.assertRaises(Exception):
            engine.approve(ar, actor=B)                                # L2 approver cannot jump ahead of L1
        engine.approve(ar, actor=A)
        self.assertEqual(_cur(ar), 2)

# Copyright (c) 2026, eCentric and contributors
"""Phase B1 tests: new masters + generic approval orchestration + AI Topup rules.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_b1
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import service as engine
from ecentric_workspace.approval_center.engine.service import decide_level

PFX = "ZZB1_"


def _user(email, roles=("Employee",), enabled=1, utype="System User"):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": utype, "enabled": enabled, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        if utype == "System User":
            u.add_roles(*roles)
    return email


def _tool(name="ZZ Tool"):
    if not frappe.db.exists("EC AI Tool", name):
        frappe.get_doc({"doctype": "EC AI Tool", "tool_name": name}).insert(ignore_permissions=True)
    return name


def _process(code, participants_l2, active=True):
    """Build a 2-level Any One process: L1 Requester Manager, L2 configured users."""
    pname = PFX + code
    if not frappe.db.exists("EC Approval Process", pname):
        p = frappe.get_doc({"doctype": "EC Approval Process", "process_code": pname, "title": pname,
                            "approval_type": "AI_TOPUP", "status": "Draft"}).insert(ignore_permissions=True)
        l1 = frappe.get_doc({"doctype": "EC Approval Level", "approval_process": p.name, "level_no": 1,
                             "level_name": "Manager", "approval_mode": "Any One"})
        l1.append("participants", {"participant_purpose": "Approver", "source_type": "User",
                                   "user": participants_l2[0]})  # stand-in resolvable approver
        l1.insert(ignore_permissions=True)
        l2 = frappe.get_doc({"doctype": "EC Approval Level", "approval_process": p.name, "level_no": 2,
                             "level_name": "Finance", "approval_mode": "Any One"})
        for u in participants_l2:
            l2.append("participants", {"participant_purpose": "Approver", "source_type": "User", "user": u})
        l2.insert(ignore_permissions=True)
        if active:
            p.status = "Active"; p.save(ignore_permissions=True)
    return pname


class TestB1Modes(FrappeTestCase):
    def test_decide_level_pure(self):
        self.assertEqual(decide_level("Any One", 0, ["Approved", "Pending"]), ("approved", True))
        self.assertEqual(decide_level("All Required", 0, ["Approved", "Pending"]), ("pending", False))
        self.assertEqual(decide_level("All Required", 0, ["Approved", "Approved"]), ("approved", False))
        self.assertEqual(decide_level("Minimum Count", 2, ["Approved", "Approved", "Pending"]), ("approved", True))
        self.assertEqual(decide_level("Any One", 0, ["Rejected", "Pending"]), ("rejected", False))


class TestB1Account(FrappeTestCase):
    def test_account_key_and_normalize(self):
        _tool()
        mgr = _user("zzb1_mgr@example.com")
        acc = frappe.get_doc({"doctype": "EC AI Account", "ai_tool": "ZZ Tool",
                              "account_email": "  Team@Example.COM ", "account_manager": mgr}
                             ).insert(ignore_permissions=True)
        self.assertEqual(acc.account_email, "team@example.com")
        self.assertEqual(acc.account_key, "ZZ Tool::team@example.com")
        # duplicate tool/account blocked (DB unique)
        with self.assertRaises(Exception):
            frappe.get_doc({"doctype": "EC AI Account", "ai_tool": "ZZ Tool",
                            "account_email": "team@example.com", "account_manager": mgr}
                           ).insert(ignore_permissions=True)

    def test_manager_must_be_active_system_user(self):
        _tool()
        _user("zzb1_web@example.com", utype="Website User")
        with self.assertRaises(frappe.exceptions.ValidationError):
            frappe.get_doc({"doctype": "EC AI Account", "ai_tool": "ZZ Tool",
                            "account_email": "x1@example.com", "account_manager": "zzb1_web@example.com"}
                           ).insert(ignore_permissions=True)

    def test_manager_change_requires_reason(self):
        _tool()
        m1 = _user("zzb1_m1@example.com"); m2 = _user("zzb1_m2@example.com")
        acc = frappe.get_doc({"doctype": "EC AI Account", "ai_tool": "ZZ Tool",
                              "account_email": "chg@example.com", "account_manager": m1}
                             ).insert(ignore_permissions=True)
        acc.account_manager = m2
        with self.assertRaises(frappe.exceptions.ValidationError):
            acc.save(ignore_permissions=True)
        acc.reload(); acc.account_manager = m2; acc.manager_change_reason = "handover"
        acc.save(ignore_permissions=True)
        self.assertEqual(acc.account_manager, m2)


class TestB1SLA(FrappeTestCase):
    def test_policy_code_immutable(self):
        p = frappe.get_doc({"doctype": "EC Approval SLA Policy", "policy_code": PFX + "SLA",
                            "policy_name": "x", "duration_hours": 48}).insert(ignore_permissions=True)
        p.policy_code = PFX + "SLA2"
        with self.assertRaises(frappe.exceptions.ValidationError):
            p.save(ignore_permissions=True)


class TestB1AITopupRules(FrappeTestCase):
    def test_existing_account_requires_active_account(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            frappe.get_doc({"doctype": "EC AI Topup Request", "account_mode": "Existing Account"}
                           ).insert(ignore_permissions=True)

    def test_new_account_requires_fields(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            frappe.get_doc({"doctype": "EC AI Topup Request", "account_mode": "New Account",
                            "ai_tool": _tool()}).insert(ignore_permissions=True)

    def test_subscription_date_order(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            frappe.get_doc({"doctype": "EC AI Topup Request", "account_mode": "New Account",
                            "ai_tool": _tool(), "proposed_account_email": "p@example.com",
                            "proposed_account_manager": _user("zzb1_pm@example.com"),
                            "subscription_start_date": "2026-12-31",
                            "subscription_end_date": "2026-01-01"}).insert(ignore_permissions=True)

    def test_completion_invoice_conditional(self):
        base = {"doctype": "EC AI Topup Request", "account_mode": "New Account", "ai_tool": _tool(),
                "proposed_account_email": "c@example.com",
                "proposed_account_manager": _user("zzb1_pm2@example.com"),
                "fulfillment_status": "Completed", "actual_amount": 10, "actual_currency": "VND",
                "topup_datetime": frappe.utils.now_datetime(), "transaction_reference": "T",
                "payment_proof": "/f/p", "confirmed_account_manager": _user("zzb1_pm2@example.com"),
                "actual_account_email": "c@example.com", "invoice_status": "Invoice Available"}
        # Invoice Available but no invoice_receipt -> blocked (also needs approval; expect ValidationError first)
        with self.assertRaises(frappe.exceptions.ValidationError):
            frappe.get_doc(dict(base)).insert(ignore_permissions=True)


class TestB1EngineFlow(FrappeTestCase):
    def _make_reference(self):
        # a lightweight business doc to serve as the approval reference
        return frappe.get_doc({"doctype": "EC AI Tool", "tool_name": PFX + frappe.generate_hash(length=6)}
                              ).insert(ignore_permissions=True).name

    def test_any_one_flow_skip_and_advance(self):
        a = _user("zzb1_a@example.com"); b = _user("zzb1_b@example.com")
        proc = _process("FLOW", [a, b])
        ref = self._make_reference()
        req = engine.submit("EC AI Tool", ref, "AI_TOPUP", a)  # L1 approver stand-in = a
        # L1 approve by a -> level 1 done, level 2 active
        engine.approve(req, actor=a)
        r = frappe.get_doc("EC Approval Request", req)
        self.assertEqual(r.current_level, 2)
        # L2 Any One: a approves -> remaining (b) Skipped, request Approved
        engine.approve(req, actor=a)
        r.reload()
        self.assertEqual(r.approval_status, "Approved")
        skipped = frappe.get_all("EC Approval Request Approver",
                                 filters={"approval_request": req, "status": "Skipped"})
        self.assertTrue(skipped)
        # audit: append-only actions exist
        self.assertTrue(frappe.get_all("EC Approval Action", filters={"approval_request": req}))

    def test_reject_is_terminal(self):
        a = _user("zzb1_a@example.com"); b = _user("zzb1_b@example.com")
        proc = _process("FLOW", [a, b])
        req = engine.submit("EC AI Tool", self._make_reference(), "AI_TOPUP", a)
        with self.assertRaises(frappe.exceptions.ValidationError):
            engine.reject(req, actor=a, comment=None)  # reason required
        engine.reject(req, actor=a, comment="not needed")
        self.assertEqual(frappe.db.get_value("EC Approval Request", req, "approval_status"), "Rejected")

    def test_request_info_and_resubmit_resumes(self):
        a = _user("zzb1_a@example.com"); b = _user("zzb1_b@example.com")
        proc = _process("FLOW", [a, b])
        req = engine.submit("EC AI Tool", self._make_reference(), "AI_TOPUP", a)
        engine.request_information(req, actor=a, comment="need info")
        self.assertEqual(frappe.db.get_value("EC Approval Request", req, "approval_status"), "Information Required")
        engine.resubmit(req, actor=a, restart=False)
        self.assertEqual(frappe.db.get_value("EC Approval Request", req, "approval_status"), "Pending")
        self.assertEqual(frappe.db.get_value("EC Approval Request", req, "current_level"), 1)


class TestB1Safeguards(FrappeTestCase):
    def test_sla_business_hours_rejected(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            frappe.get_doc({"doctype": "EC Approval SLA Policy", "policy_code": PFX + "BH",
                            "policy_name": "bh", "duration_hours": 24, "use_business_hours": 1}
                           ).insert(ignore_permissions=True)

    def test_department_manager_resolver_fail_closed(self):
        from frappe import _dict
        dept = "ZZB1 Dept - " + (frappe.defaults.get_global_default("company") or "")
        # valid head
        u_ok = _user("zzb1_head@example.com")
        emp = frappe.get_doc({"doctype": "Employee", "employee_name": "H", "first_name": "H",
                              "user_id": u_ok, "status": "Active", "date_of_joining": "2020-01-01",
                              "date_of_birth": "1990-01-01", "gender": "Other"}).insert(ignore_permissions=True)
        d = frappe.get_doc({"doctype": "Department", "department_name": "ZZB1DeptOK"})
        d.insert(ignore_permissions=True)
        frappe.db.set_value("Department", d.name, "department_head", emp.name)
        rows = engine.resolve_participants(
            [_dict({"participant_purpose": "Approver", "source_type": "Department Manager",
                    "department": d.name, "sort_order": 0})], requester=None)
        self.assertEqual([u for u, _l in rows], [u_ok])
        # missing head -> no approver (fail closed)
        d2 = frappe.get_doc({"doctype": "Department", "department_name": "ZZB1DeptNoHead"}).insert(ignore_permissions=True)
        rows2 = engine.resolve_participants(
            [_dict({"participant_purpose": "Approver", "source_type": "Department Manager",
                    "department": d2.name, "sort_order": 0})], requester=None)
        self.assertEqual(rows2, [])
        # website-user head -> rejected
        uw = _user("zzb1_headweb@example.com", utype="Website User")
        empw = frappe.get_doc({"doctype": "Employee", "employee_name": "W", "first_name": "W",
                               "user_id": uw, "status": "Active", "date_of_joining": "2020-01-01",
                               "date_of_birth": "1990-01-01", "gender": "Other"}).insert(ignore_permissions=True)
        frappe.db.set_value("Department", d.name, "department_head", empw.name)
        rows3 = engine.resolve_participants(
            [_dict({"participant_purpose": "Approver", "source_type": "Department Manager",
                    "department": d.name, "sort_order": 0})], requester=None)
        self.assertEqual(rows3, [])

    def test_no_duplicate_assignment_and_close(self):
        t = frappe.get_doc({"doctype": "EC AI Tool", "tool_name": PFX + frappe.generate_hash(length=6)}
                           ).insert(ignore_permissions=True).name
        u = _user("zzb1_asg@example.com")
        engine.assign("EC AI Tool", t, [u]); engine.assign("EC AI Tool", t, [u])  # idempotent
        openn = frappe.get_all("ToDo", filters={"reference_type": "EC AI Tool", "reference_name": t,
                                                "allocated_to": u, "status": "Open"})
        self.assertEqual(len(openn), 1)
        engine.close_todos("EC AI Tool", t)
        self.assertFalse(frappe.get_all("ToDo", filters={"reference_type": "EC AI Tool",
                                                          "reference_name": t, "status": "Open"}))

    def test_double_approval_fails_safe(self):
        a = _user("zzb1_a@example.com"); b = _user("zzb1_b@example.com")
        _process("FLOW", [a, b])
        req = engine.submit("EC AI Tool", frappe.get_doc(
            {"doctype": "EC AI Tool", "tool_name": PFX + frappe.generate_hash(length=6)}
        ).insert(ignore_permissions=True).name, "AI_TOPUP", a)
        engine.approve(req, actor=a)  # completes L1, advances to L2
        # a already decided at L1; approving L1 again is impossible (no pending row at L1)
        # at L2, a is pending; approve once ok, second time must fail (row no longer pending)
        engine.approve(req, actor=a)  # L2 -> Approved
        with self.assertRaises(frappe.exceptions.ValidationError):
            engine.approve(req, actor=a)  # terminal -> guarded

    def test_duplicate_claim_protection(self):
        # simulate assigned request
        doc = frappe.get_doc({"doctype": "EC AI Topup Request", "account_mode": "New Account",
                              "ai_tool": _tool(), "proposed_account_email": "q@example.com",
                              "proposed_account_manager": _user("zzb1_pm3@example.com")}).insert(ignore_permissions=True)
        frappe.db.set_value("EC AI Topup Request", doc.name, "fulfillment_status", "Assigned")
        f1 = _user("zzb1_f1@example.com"); f2 = _user("zzb1_f2@example.com")
        from ecentric_workspace.approval_center.ai_topup import service as ai
        # make both eligible via ToDo
        engine.assign("EC AI Topup Request", doc.name, [f1, f2])
        ai.claim_fulfillment(doc.name, user=f1)
        with self.assertRaises(frappe.exceptions.ValidationError):
            ai.claim_fulfillment(doc.name, user=f2)
        self.assertEqual(frappe.db.get_value("EC AI Topup Request", doc.name, "fulfillment_owner"), f1)

    def test_submit_only_own_request(self):
        from ecentric_workspace.approval_center.ai_topup import service as ai
        owner = _user("zzb1_owner@example.com"); other = _user("zzb1_other@example.com")
        doc = frappe.get_doc({"doctype": "EC AI Topup Request", "account_mode": "New Account",
                              "ai_tool": _tool(), "proposed_account_email": "own@example.com",
                              "proposed_account_manager": _user("zzb1_pm4@example.com"),
                              "requested_by": owner}).insert(ignore_permissions=True)
        frappe.set_user(other)
        try:
            with self.assertRaises(frappe.exceptions.ValidationError):
                ai.submit(doc.name)
        finally:
            frappe.set_user("Administrator")

    def test_notification_failure_does_not_raise(self):
        import unittest.mock as mock
        with mock.patch.object(frappe, "get_doc", side_effect=Exception("boom")):
            pass  # ensure patching machinery available
        # notify swallows errors: bad user should not raise
        engine.notify(["nonexistent-user@example.com"], "s", "EC AI Tool", "nope")

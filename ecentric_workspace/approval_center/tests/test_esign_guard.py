# Copyright (c) 2026, eCentric and contributors
"""Guard tests - the security core of S2A (user directives 2026-07-11):
  * NO role bypass: plain approve AND admin override fail closed on signature levels.
  * frappe.flags is a call marker only: a forged flag without a persisted verified
    DSR (or with a mismatched one) is rejected by DB validation.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_guard
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import payment_request as papi
from ecentric_workspace.approval_center.engine import service as engine
from ecentric_workspace.approval_center.esign import guard, service as esvc
from ecentric_workspace.approval_center.tests import esign_fixtures as fx


class TestEsignGuard(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")
        setattr(frappe.flags, guard.FLAG_KEY, None)

    # ------------------------------------------------------------------ #
    def test_plain_approve_blocked_on_signature_level_for_every_role(self):
        h = fx.full_stack(fx.PFX + "g1r@example.com", fx.PFX + "g1m@example.com")
        # approver (mgr, L1) via the normal form API -> blocked
        frappe.set_user(h["mgr"])
        with self.assertRaises(frappe.PermissionError):
            papi.approve(h["biz"])
        frappe.set_user("Administrator")
        # direct engine call as Administrator -> blocked too (no role bypass)
        with self.assertRaises(frappe.PermissionError):
            engine.approve(h["ar"], actor=h["mgr"])
        st = frappe.db.get_value("EC Approval Request", h["ar"],
                                 ["approval_status", "current_level"], as_dict=True)
        self.assertEqual((st.approval_status, st.current_level), ("Pending", 1))

    def test_admin_override_blocked_on_signature_level(self):
        h = fx.full_stack(fx.PFX + "g2r@example.com", fx.PFX + "g2m@example.com")
        with self.assertRaises(frappe.PermissionError):
            engine.admin_override_current_level(h["ar"], actor="Administrator",
                                                reason="attempted break-glass")
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "approval_status"), "Pending")

    def test_forged_flag_without_persisted_dsr_is_rejected(self):
        h = fx.full_stack(fx.PFX + "g3r@example.com", fx.PFX + "g3m@example.com")
        setattr(frappe.flags, guard.FLAG_KEY, "EC-DSR-2026-99999")  # nonexistent
        with self.assertRaises(frappe.PermissionError):
            engine.approve(h["ar"], actor=h["mgr"])

    def test_flag_with_unverified_dsr_is_rejected(self):
        h = fx.full_stack(fx.PFX + "g4r@example.com", fx.PFX + "g4m@example.com")
        frappe.set_user(h["mgr"])
        res = esvc.approve_and_sign("EC Payment Request", h["biz"])  # Queued, NOT signed
        frappe.set_user("Administrator")
        setattr(frappe.flags, guard.FLAG_KEY, res["signature_request"])
        with self.assertRaises(frappe.PermissionError):
            engine.approve(h["ar"], actor=h["mgr"])  # dsr_not_in_signed_state

    def test_flag_with_wrong_actor_is_rejected(self):
        h = fx.full_stack(fx.PFX + "g5r@example.com", fx.PFX + "g5m@example.com")
        frappe.set_user(h["mgr"])
        res = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        dsr = res["signature_request"]
        # push the DSR to Signed through the worker, then try completing as OTHER user
        fx.run_worker_for_latest(h["ar"])
        status = frappe.db.get_value("EC Digital Signature Request", dsr, "status")
        if status == "Approval Completed":
            self.skipTest("worker completed L1 in-line; actor-mismatch covered by unit path")
        setattr(frappe.flags, guard.FLAG_KEY, dsr)
        # denial may surface as the engine's own pending-approver ValidationError
        # (fires before the guard) or the guard's PermissionError - both fail-closed.
        with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
            engine.approve(h["ar"], actor=fx.FIN)  # FIN is not L1's approver row owner

    def test_non_profiled_type_unchanged(self):
        # no enabled profile for this fresh type context -> guard is a no-op
        fx.ensure_process()
        fx.ensure_profile(enabled=False)
        mgr = fx.user(fx.PFX + "g6m@example.com")
        requester = fx.user(fx.PFX + "g6r@example.com")
        fx.employee(requester, reports_to=fx.employee(mgr))
        biz = fx.draft_payment_request(requester)
        frappe.set_user(requester); papi.submit_request(biz); frappe.set_user("Administrator")
        frappe.set_user(mgr); papi.approve(biz); frappe.set_user("Administrator")
        ar = frappe.db.get_value("EC Payment Request", biz, "approval_request")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)

    def test_gates_closed_restores_plain_approve(self):
        # designed rollback: profile enabled but settings gates OFF -> normal approve works
        h = fx.full_stack(fx.PFX + "g7r@example.com", fx.PFX + "g7m@example.com")
        fx.ensure_settings(enabled=False)
        frappe.set_user(h["mgr"]); papi.approve(h["biz"]); frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 2)

    def test_stale_package_hash_rejected_at_completion(self):
        h = fx.full_stack(fx.PFX + "g8r@example.com", fx.PFX + "g8m@example.com")
        frappe.set_user(h["mgr"])
        res = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        dsr = res["signature_request"]
        # simulate package drift AFTER the DSR was created & verified
        frappe.db.set_value("EC Digital Signature Request", dsr,
                            {"status": "Signed", "verified_at": frappe.utils.now_datetime()})
        frappe.db.set_value("EC Digital Signature Package", h["pkg"],
                            "package_hash", "f" * 64)
        setattr(frappe.flags, guard.FLAG_KEY, dsr)
        with self.assertRaises(frappe.PermissionError):
            engine.approve(h["ar"], actor=h["mgr"])  # package_hash_mismatch

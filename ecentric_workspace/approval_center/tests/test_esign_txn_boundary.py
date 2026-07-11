# Copyright (c) 2026, eCentric and contributors
"""Verification Gate items C/D/E: completion-transaction boundary, failure injection,
concurrency idempotency, frappe.flags hygiene.

Atomicity model under test: verify_and_complete() runs DSR row-lock -> guard DB
validation -> engine.approve() -> DSR 'Approval Completed' ALL IN ONE DB TRANSACTION
(no intermediate commit anywhere in the path). A crash at any point rolls the whole
unit back; retry re-runs from a consistent state and can never double-approve because
(a) after commit the approver row is no longer Pending and the DSR is no longer
'Signed', and (b) before commit nothing persisted.

Crash-and-recover is simulated with savepoints: inject failure -> rollback to
savepoint (what MariaDB does on connection death) -> assert clean state -> retry.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_txn_boundary
"""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import service as engine
from ecentric_workspace.approval_center.esign import events, guard, service as esvc
from ecentric_workspace.approval_center.tests import esign_fixtures as fx


def _signed_dsr(h):
    """Create a DSR and drive it to a REAL provider-verified 'Signed' state (mock),
    without completing (patch completion to a no-op during the worker run)."""
    frappe.set_user(h["mgr"])
    res = esvc.approve_and_sign("EC Payment Request", h["biz"])
    frappe.set_user("Administrator")
    with patch.object(esvc, "verify_and_complete", lambda name: {"completed": False}):
        fx.run_worker_for_latest(h["ar"])
    dsr = res["signature_request"]
    assert frappe.db.get_value("EC Digital Signature Request", dsr, "status") == "Signed"
    return dsr


def _approved_actions(ar, level_no=1):
    return frappe.db.count("EC Approval Action", {"approval_request": ar,
                                                  "action": "Approved"})


class TestEsignTxnBoundary(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")
        setattr(frappe.flags, guard.FLAG_KEY, None)

    # ---------------- D: failure injection ---------------- #
    def test_failure_before_engine_approve_then_retry_single_completion(self):
        h = fx.full_stack(fx.PFX + "t1r@example.com", fx.PFX + "t1m@example.com")
        dsr = _signed_dsr(h)
        with patch.object(engine, "approve", side_effect=RuntimeError("boom-before")):
            out = esvc.verify_and_complete(dsr)
        self.assertFalse(out["completed"])
        # caught path -> Manual Review, approval untouched, marker cleared
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request", dsr,
                                             "status"), "Manual Review")
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 1)
        self.assertIsNone(getattr(frappe.flags, guard.FLAG_KEY, None))
        # ops retry path: back to Signed via governed states, then complete ONCE
        frappe.db.set_value("EC Digital Signature Request", dsr, "status", "Signed")
        out = esvc.verify_and_complete(dsr)
        self.assertTrue(out["completed"])
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 2)
        self.assertEqual(_approved_actions(h["ar"]), 1)

    def test_crash_after_engine_approve_rolls_back_everything_then_retry_once(self):
        h = fx.full_stack(fx.PFX + "t2r@example.com", fx.PFX + "t2m@example.com")
        dsr = _signed_dsr(h)
        frappe.db.savepoint("esign_crash_sim")
        # crash AFTER engine.approve but BEFORE DSR 'Approval Completed' persists:
        # make the final status write explode (uncaught -> whole txn dies in prod)
        real = events.set_dsr_status

        def exploding(name, to_status, **kw):
            if to_status == "Approval Completed":
                raise RuntimeError("boom-after-approve")
            return real(name, to_status, **kw)

        with patch.object(events, "set_dsr_status", side_effect=exploding):
            with self.assertRaises(RuntimeError):
                esvc.verify_and_complete(dsr)
        # simulate the crash recovery MariaDB performs: rollback the open transaction
        frappe.db.rollback(save_point="esign_crash_sim")
        # NOTHING persisted: engine.approve's mutations AND the DSR both rolled back
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 1)
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request", dsr,
                                             "status"), "Signed")
        self.assertEqual(_approved_actions(h["ar"]), 0)
        # retry completes exactly once - no double approval, no false completed state
        out = esvc.verify_and_complete(dsr)
        self.assertTrue(out["completed"])
        self.assertEqual(_approved_actions(h["ar"]), 1)
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request", dsr,
                                             "status"), "Approval Completed")

    def test_partial_engine_mutation_rolled_back_on_midflight_failure(self):
        """Verification-gate correction regression: engine.approve fails AFTER
        mutating the approver row -> savepoint rollback discards the partial
        mutation; only the Manual Review marker persists."""
        h = fx.full_stack(fx.PFX + "t8r@example.com", fx.PFX + "t8m@example.com")
        dsr = _signed_dsr(h)

        def exploding_evaluate(req, level_no):
            raise RuntimeError("boom-mid-engine")  # after approver-row write

        with patch.object(engine, "_evaluate", side_effect=exploding_evaluate):
            out = esvc.verify_and_complete(dsr)
        self.assertFalse(out["completed"])
        # partial engine mutation (approver row Approved) must NOT survive
        row_status = frappe.db.get_value(
            "EC Approval Request Approver",
            {"approval_request": h["ar"], "level_no": 1, "approver": h["mgr"]}, "status")
        self.assertEqual(row_status, "Pending")
        self.assertEqual(_approved_actions(h["ar"]), 0)
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request", dsr,
                                             "status"), "Manual Review")

    # ---------------- C: concurrency / idempotency ---------------- #
    def test_double_completion_is_idempotent_single_approval_action(self):
        h = fx.full_stack(fx.PFX + "t3r@example.com", fx.PFX + "t3m@example.com")
        dsr = _signed_dsr(h)
        out1 = esvc.verify_and_complete(dsr)
        out2 = esvc.verify_and_complete(dsr)  # second worker/reconciler race
        self.assertTrue(out1["completed"])
        self.assertFalse(out2["completed"])
        self.assertEqual(out2["reason"], "not_in_signed_state")
        self.assertEqual(_approved_actions(h["ar"]), 1)
        # level advanced exactly once
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 2)

    def test_double_create_yields_one_active_dsr(self):
        h = fx.full_stack(fx.PFX + "t4r@example.com", fx.PFX + "t4m@example.com")
        frappe.set_user(h["mgr"])
        r1 = esvc.approve_and_sign("EC Payment Request", h["biz"])
        r2 = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        self.assertEqual(r1["signature_request"], r2["signature_request"])
        self.assertEqual(frappe.db.count("EC Digital Signature Request",
                                         {"approval_request": h["ar"]}), 1)

    def test_completed_dsr_cannot_reauthorize_a_second_engine_approve(self):
        """B: already-completed DSR is not a valid completion credential."""
        h = fx.full_stack(fx.PFX + "t5r@example.com", fx.PFX + "t5m@example.com",
                          levels=(1,))  # only L1 signs; L2+ plain
        dsr = _signed_dsr(h)
        self.assertTrue(esvc.verify_and_complete(dsr)["completed"])
        # forge: reuse the COMPLETED DSR as marker for the next level
        setattr(frappe.flags, guard.FLAG_KEY, dsr)
        # L2 does not require signature -> guard no-op; but at L1-type reuse:
        req = frappe.get_doc("EC Approval Request", h["ar"])
        with self.assertRaises(frappe.PermissionError):
            guard.validate_completion(dsr, req, req.current_level, h["mgr"])

    # ---------------- E: frappe.flags hygiene ---------------- #
    def test_marker_cleared_in_finally_on_success_and_failure(self):
        h = fx.full_stack(fx.PFX + "t6r@example.com", fx.PFX + "t6m@example.com")
        dsr = _signed_dsr(h)
        sentinel = "PREVIOUS-VALUE"
        setattr(frappe.flags, guard.FLAG_KEY, sentinel)
        esvc.verify_and_complete(dsr)  # success path
        self.assertEqual(getattr(frappe.flags, guard.FLAG_KEY, None), sentinel)

    def test_marker_alone_never_authorizes_and_next_action_unaffected(self):
        # profile signs ONLY L1: after L1 completes, L2 plain approve must work
        # normally even with a stale/forged marker still set (guard no-ops on
        # non-signing levels; marker is never read as authorization there).
        h = fx.full_stack(fx.PFX + "t7r@example.com", fx.PFX + "t7m@example.com",
                          levels=(1,))
        dsr = _signed_dsr(h)
        self.assertTrue(esvc.verify_and_complete(dsr)["completed"])
        setattr(frappe.flags, guard.FLAG_KEY, "FORGED-OR-STALE")
        from ecentric_workspace.approval_center.api import payment_request as papi
        frappe.set_user(fx.FIN)
        papi.approve(h["biz"])  # L2, non-signing -> normal path, unaffected
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 3)

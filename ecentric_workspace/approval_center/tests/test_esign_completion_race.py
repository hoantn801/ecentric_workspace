# Copyright (c) 2026, eCentric and contributors
"""R2 regression (2026-07-12): terminal state is preserved during completion races.

Covers the required behaviors:
  * a loser that raced a winner exits as an idempotent no-op (no Manual Review,
    no misleading failure/manual-review event);
  * Approval Completed is never downgraded;
  * a genuine single-worker failure still stamps Manual Review (conditional write
    succeeds because the attempt still owns the Signed state);
  * winner repairs a racer's Manual Review label to the true terminal outcome;
  * exactly one Approved action / one level transition / one completion under
    repeated in-process double-completion.

The true two-OS-process races are exercised at gate time (bench execute x2 in
parallel); these tests simulate every interleaving deterministically.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_completion_race
"""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import service as engine
from ecentric_workspace.approval_center.esign import guard, service as esvc
from ecentric_workspace.approval_center.tests import esign_fixtures as fx


def _signed_dsr(h):
    frappe.set_user(h["mgr"])
    res = esvc.approve_and_sign("EC Payment Request", h["biz"])
    frappe.set_user("Administrator")
    with patch.object(esvc, "verify_and_complete", lambda name: {"completed": False}):
        fx.run_worker_for_latest(h["ar"])
    assert frappe.db.get_value("EC Digital Signature Request",
                               res["signature_request"], "status") == "Signed"
    return res["signature_request"]


def _approved(ar):
    return frappe.db.count("EC Approval Action", {"approval_request": ar, "action": "Approved"})


def _mr_events(dsr):
    return frappe.db.count("EC Digital Signature Event",
                           {"signature_request": dsr, "event_type": "ManualReview"})


class TestCompletionRace(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")
        setattr(frappe.flags, guard.FLAG_KEY, None)

    def test_loser_write_refuses_winner_terminal_state_no_mr_event(self):
        """The exact loser write the except-branch performs must refuse a committed
        terminal state and emit NO Manual Review event; a fresh loser attempt on the
        terminal row exits as an idempotent no-op. (The cross-process race window
        itself cannot be reproduced in one transaction while the entry lock is held -
        that is what the conditional write defends; the two-OS-process Race B at gate
        time exercises the live window.)"""
        h = fx.full_stack(fx.PFX + "cr1r@example.com", fx.PFX + "cr1m@example.com")
        dsr = _signed_dsr(h)
        # winner's committed terminal result
        frappe.db.sql("""UPDATE `tabEC Digital Signature Request`
                         SET status='Approval Completed' WHERE name=%s""", (dsr,))
        # loser's guarded Manual Review write (identical call to the except-branch)
        changed = esvc._guarded_dsr_transition(
            dsr, "Signed", "Manual Review",
            extra={"manual_review_reason": "loser"}, event_type="ManualReview")
        self.assertFalse(changed)  # refused: current state was not Signed
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request", dsr,
                                             "status"), "Approval Completed")
        self.assertEqual(_mr_events(dsr), 0)  # no misleading event
        # a full loser re-entry on the terminal row is an idempotent no-op
        out = esvc.verify_and_complete(dsr)
        self.assertFalse(out["completed"])
        self.assertEqual(out["reason"], "not_in_signed_state")

    def test_genuine_failure_still_stamps_manual_review(self):
        h = fx.full_stack(fx.PFX + "cr2r@example.com", fx.PFX + "cr2m@example.com")
        dsr = _signed_dsr(h)
        with patch.object(engine, "approve", side_effect=RuntimeError("genuine")):
            out = esvc.verify_and_complete(dsr)
        self.assertEqual(out["reason"], "engine_refused")
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request", dsr,
                                             "status"), "Manual Review")
        self.assertEqual(_mr_events(dsr), 1)

    def test_winner_repairs_racer_manual_review_label(self):
        """Racing loser stamped Manual Review between the winner's engine.approve and
        its final write -> winner upgrades the label to Approval Completed."""
        h = fx.full_stack(fx.PFX + "cr3r@example.com", fx.PFX + "cr3m@example.com")
        dsr = _signed_dsr(h)
        real_approve = engine.approve

        def approve_then_racer_stamps_mr(*a, **kw):
            real_approve(*a, **kw)  # the winner's genuine engine completion
            frappe.db.sql("""UPDATE `tabEC Digital Signature Request`
                             SET status='Manual Review' WHERE name=%s""", (dsr,))

        with patch.object(engine, "approve", side_effect=approve_then_racer_stamps_mr):
            out = esvc.verify_and_complete(dsr)
        self.assertTrue(out["completed"])
        self.assertEqual(out.get("note"), "repaired_racer_manual_review_label")
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request", dsr,
                                             "status"), "Approval Completed")
        self.assertEqual(_approved(h["ar"]), 1)
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 2)

    def test_terminal_never_downgraded_by_direct_transition(self):
        h = fx.full_stack(fx.PFX + "cr4r@example.com", fx.PFX + "cr4m@example.com")
        dsr = _signed_dsr(h)
        self.assertTrue(esvc.verify_and_complete(dsr)["completed"])
        # any further attempt to stamp Manual Review is a guarded no-op
        self.assertFalse(esvc._guarded_dsr_transition(dsr, "Signed", "Manual Review"))
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request", dsr,
                                             "status"), "Approval Completed")
        # and the state machine itself has no exit from Approval Completed
        from ecentric_workspace.approval_center.esign import state as sm
        self.assertEqual(sm.DSR_TRANSITIONS["Approval Completed"], ())

    def test_repeated_double_completion_exactly_once(self):
        """Repeated in-process double completions (worker + reconciler re-entry):
        exactly one Approved action, one level transition, one completion; every
        loser returns a safe no-op; no ToDo duplication for the next level."""
        h = fx.full_stack(fx.PFX + "cr5r@example.com", fx.PFX + "cr5m@example.com")
        dsr = _signed_dsr(h)
        results = [esvc.verify_and_complete(dsr) for _ in range(5)]
        self.assertEqual(sum(1 for r in results if r.get("completed") and not r.get("note")), 1)
        self.assertTrue(all(r.get("reason") == "not_in_signed_state"
                            for r in results[1:]))
        self.assertEqual(_approved(h["ar"]), 1)
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 2)
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request", dsr,
                                             "status"), "Approval Completed")
        self.assertEqual(_mr_events(dsr), 0)
        # next-level assignment exists exactly once (no duplicate ToDo)
        nxt = frappe.db.count("ToDo", {"reference_type": "EC Payment Request",
                                       "reference_name": h["biz"], "status": "Open"})
        self.assertEqual(nxt, 1)  # single L2 approver ToDo

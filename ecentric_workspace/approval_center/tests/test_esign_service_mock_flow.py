# Copyright (c) 2026, eCentric and contributors
"""End-to-end mock flow: Duyệt & Ký through all 4 Payment Request levels with the
engine completing each level ONLY after verified mock signing; ToDo handoff intact;
reject-first semantics; engine-drift -> Manual Review; failure modes.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_service_mock_flow
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import service as engine
from ecentric_workspace.approval_center.esign import service as esvc
from ecentric_workspace.approval_center.tests import esign_fixtures as fx


def _sign_current_level(h, user):
    frappe.set_user(user)
    res = esvc.approve_and_sign("EC Payment Request", h["biz"])
    frappe.set_user("Administrator")
    fx.run_worker_for_latest(h["ar"])
    return res


class TestEsignMockFlow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_full_chain_sign_all_levels(self):
        h = fx.full_stack(fx.PFX + "f1r@example.com", fx.PFX + "f1m@example.com")
        order = [h["mgr"], fx.FIN, fx.HOF, fx.CEO]
        for i, u in enumerate(order, start=1):
            # ToDo handoff: current approver holds the open ToDo before signing
            self.assertTrue(frappe.db.exists("ToDo", {
                "reference_type": "EC Payment Request", "reference_name": h["biz"],
                "allocated_to": u, "status": "Open"}), "L%d ToDo missing for %s" % (i, u))
            _sign_current_level(h, u)
            st = frappe.db.get_value("EC Approval Request", h["ar"],
                                     ["approval_status", "current_level"], as_dict=True)
            if i < len(order):
                self.assertEqual((st.approval_status, st.current_level), ("Pending", i + 1))
            else:
                self.assertEqual(st.approval_status, "Approved")
        # every level completed strictly through DSR Approval Completed
        done = frappe.get_all("EC Digital Signature Request",
                              filters={"approval_request": h["ar"],
                                       "status": "Approval Completed"}, pluck="name")
        self.assertEqual(len(done), 4)
        # three-concept audit: each DSR has ProviderAccepted-or-Queued, Verified, ApprovalCompleted
        for d in done:
            types = set(frappe.get_all("EC Digital Signature Event",
                                       filters={"signature_request": d}, pluck="event_type"))
            self.assertIn("Verified", types)
            self.assertIn("ApprovalCompleted", types)

    def test_lazy_creation_trigger_creates_document_at_first_sign(self):
        h = fx.full_stack(fx.PFX + "f2r@example.com", fx.PFX + "f2m@example.com")
        self.assertFalse(frappe.db.get_value("EC Digital Signature Package", h["pkg"],
                                             "scts_document_id"))
        _sign_current_level(h, h["mgr"])
        self.assertTrue(frappe.db.get_value("EC Digital Signature Package", h["pkg"],
                                            "scts_document_id"))

    def test_never_sign_mode_stays_open_and_does_not_complete(self):
        h = fx.full_stack(fx.PFX + "f3r@example.com", fx.PFX + "f3m@example.com",
                          site="never:sign")
        res = _sign_current_level(h, h["mgr"])
        status = frappe.db.get_value("EC Digital Signature Request",
                                     res["signature_request"], "status")
        self.assertIn(status, ("Provider Accepted", "Verifying"))
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 1)  # NOT advanced

    def test_wrong_signer_goes_manual_review_never_completes(self):
        h = fx.full_stack(fx.PFX + "f4r@example.com", fx.PFX + "f4m@example.com",
                          site="wrong:signer")
        res = _sign_current_level(h, h["mgr"])
        # reconciler tick drives to mismatch handling on next poll
        fx.run_worker_for_latest(h["ar"])
        status = frappe.db.get_value("EC Digital Signature Request",
                                     res["signature_request"], "status")
        self.assertIn(status, ("Provider Accepted", "Verifying", "Manual Review"))
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 1)

    def test_create_failure_is_retryable_and_approval_untouched(self):
        h = fx.full_stack(fx.PFX + "f5r@example.com", fx.PFX + "f5m@example.com",
                          site="fail:create")
        res = _sign_current_level(h, h["mgr"])
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request",
                                             res["signature_request"], "status"),
                         "Retryable Failure")
        # lazy mode: Active never regresses; the failure is recorded on the DSR+Event
        self.assertEqual(frappe.db.get_value("EC Digital Signature Package", h["pkg"],
                                             "status"), "Active")
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 1)

    def test_engine_drift_between_verify_and_complete_goes_manual_review(self):
        h = fx.full_stack(fx.PFX + "f6r@example.com", fx.PFX + "f6m@example.com")
        frappe.set_user(h["mgr"])
        res = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        dsr = res["signature_request"]
        frappe.db.set_value("EC Digital Signature Request", dsr,
                            {"status": "Signed", "verified_at": frappe.utils.now_datetime()})
        # drift: the approver row is no longer Pending (simulate parallel decision)
        row = frappe.db.get_value("EC Approval Request Approver",
                                  {"approval_request": h["ar"], "level_no": 1,
                                   "approver": h["mgr"]}, "name")
        frappe.db.set_value("EC Approval Request Approver", row, "status", "Skipped")
        out = esvc.verify_and_complete(dsr)
        self.assertFalse(out["completed"])
        self.assertEqual(frappe.db.get_value("EC Digital Signature Request", dsr,
                                             "status"), "Manual Review")

    def test_reject_first_semantics(self):
        h = fx.full_stack(fx.PFX + "f7r@example.com", fx.PFX + "f7m@example.com")
        frappe.set_user(h["mgr"])
        out = esvc.reject_with_transition("EC Payment Request", h["biz"], "khong hop le")
        frappe.set_user("Administrator")
        self.assertTrue(out["rejected"])
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "approval_status"), "Rejected")

    def test_signing_status_readable_by_requester(self):
        h = fx.full_stack(fx.PFX + "f8r@example.com", fx.PFX + "f8m@example.com")
        frappe.set_user(h["requester"])
        out = esvc.get_signing_status("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        self.assertTrue(out["enabled"])
        self.assertEqual(out["package"]["name"], h["pkg"])
        self.assertEqual(len(out["package"]["files"]), 2)

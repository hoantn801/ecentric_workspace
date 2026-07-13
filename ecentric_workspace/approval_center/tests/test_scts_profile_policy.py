# Copyright (c) 2026, eCentric and contributors
"""Approver Signature Policy resolution + backward compatibility (fix/scts-profile-signing-
policy). The Approval Engine still owns approvers/order/completion; this only decides WHICH
levels are signable, WITHOUT admins recreating every level. Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_scts_profile_policy
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import guard
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

PROFILE = "ZZESN_PAYR"
BD, AT = "EC Payment Request", "PAYMENT_REQUEST"


def _policy(p):
    frappe.db.set_value("EC Digital Signature Profile", PROFILE, "approver_signature_policy", p)


def _clear_levels():
    for row in frappe.get_all("EC Digital Signature Profile Level",
                              filters={"parent": PROFILE}, pluck="name"):
        frappe.delete_doc("EC Digital Signature Profile Level", row,
                          ignore_permissions=True, force=True)


class TestApproverSignaturePolicy(FrappeTestCase):
    def setUp(self):
        fx.ensure_process()
        fx.ensure_settings(allowed_users=[fx.FIN])
        fx.ensure_profile()

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_all_levels_without_manual_rows(self):
        _clear_levels()                         # NO Signing Level rows
        _policy("All Approval Levels")
        for lv in (1, 2, 3, 4):
            self.assertTrue(guard.level_requires_signature(BD, AT, lv),
                            "level %s should be signable under All Approval Levels" % lv)

    def test_none_policy_disables_all(self):
        _policy("None")
        for lv in (1, 2, 3, 4):
            self.assertFalse(guard.level_requires_signature(BD, AT, lv))

    def test_final_level_only_uses_dynamic_final_level(self):
        _clear_levels()
        _policy("Final Approval Level Only")
        # final_level is resolved per request from frozen approvers; simulate final=4
        self.assertTrue(guard.level_requires_signature(BD, AT, 4, final_level=4))
        self.assertFalse(guard.level_requires_signature(BD, AT, 1, final_level=4))
        self.assertFalse(guard.level_requires_signature(BD, AT, 3, final_level=4))

    def test_selected_levels_uses_optional_rows(self):
        _clear_levels()
        _policy("Selected Approval Levels")
        frappe.get_doc({"doctype": "EC Digital Signature Profile Level", "parent": PROFILE,
                        "parenttype": "EC Digital Signature Profile", "parentfield": "levels",
                        "level_no": 2, "requires_signature": 1}).insert(ignore_permissions=True)
        self.assertTrue(guard.level_requires_signature(BD, AT, 2))
        self.assertFalse(guard.level_requires_signature(BD, AT, 3))

    def test_backward_compat_unset_policy_behaves_as_selected(self):
        # existing pre-migration profiles have no policy value -> OLD per-row behavior EXACTLY
        frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                            "approver_signature_policy", "")
        _clear_levels()
        frappe.get_doc({"doctype": "EC Digital Signature Profile Level", "parent": PROFILE,
                        "parenttype": "EC Digital Signature Profile", "parentfield": "levels",
                        "level_no": 1, "requires_signature": 1}).insert(ignore_permissions=True)
        self.assertTrue(guard.level_requires_signature(BD, AT, 1))   # row present
        self.assertFalse(guard.level_requires_signature(BD, AT, 2))  # no row

    def test_requester_signature_required_flag(self):
        frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                            "requester_signature_required", 1)
        self.assertTrue(guard.requester_signature_required(BD, AT))
        frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                            "requester_signature_required", 0)
        self.assertFalse(guard.requester_signature_required(BD, AT))

    def test_request_final_level_is_dynamic_per_request(self):
        # different requesters/managers => different frozen approver sets => resolved live
        h = fx.full_stack(fx.PFX + "pp1r@example.com", fx.PFX + "pp1m@example.com")
        self.assertEqual(guard.request_final_level(h["ar"]), 4)
        self.assertIsNone(guard.request_final_level(None))

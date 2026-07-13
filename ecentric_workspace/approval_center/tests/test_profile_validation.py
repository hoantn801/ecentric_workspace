# Copyright (c) 2026, eCentric and contributors
"""EC Digital Signature Profile policy-aware validation (fix/scts-profile-policy-validation).
Runs on the bench/PR CI (needs frappe DB):
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_profile_validation
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.tests import esign_fixtures as fx

DT = "EC Digital Signature Profile"


def _base(code, enabled=1, policy=None, requester=0, levels=None, deadline_rule="None"):
    fx.ensure_process()
    if frappe.db.exists(DT, code):
        frappe.delete_doc(DT, code, ignore_permissions=True, force=True)
    doc = {
        "doctype": DT, "profile_code": code, "title": code,
        "business_doctype": "EC Payment Request", "approval_type": "PAYMENT_REQUEST",
        "provider": "Mock", "environment": "UAT", "enabled": enabled,
        "provider_creation_trigger": "Before First Signing Level",
        "doc_code_source": "name", "title_source": "request_title",
        "amount_source": "payment_amount", "description_source": "reason",
        "requester_signature_required": requester, "deadline_rule": deadline_rule,
        "levels": levels or [],
    }
    if policy is not None:
        doc["approver_signature_policy"] = policy
    return frappe.get_doc(doc)


def _lvl(n, requires=1):
    return {"level_no": n, "requires_signature": requires,
            "mandatory_placements_per_file": 1}


class TestProfileValidation(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def _ok(self, doc):
        doc.insert(ignore_permissions=True)
        self.assertTrue(frappe.db.exists(DT, doc.name))
        frappe.delete_doc(DT, doc.name, ignore_permissions=True, force=True)

    def _bad(self, doc):
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_disabled_profile_no_rows_ok(self):
        self._ok(_base("ZZV_DIS", enabled=0, policy="Selected Approval Levels", levels=[]))

    def test_all_levels_zero_rows_ok(self):
        self._ok(_base("ZZV_ALL", policy="All Approval Levels", levels=[]))

    def test_final_level_only_zero_rows_ok(self):
        self._ok(_base("ZZV_FIN", policy="Final Approval Level Only", levels=[]))

    def test_selected_zero_rows_rejected(self):
        self._bad(_base("ZZV_SEL0", policy="Selected Approval Levels", levels=[]))

    def test_selected_with_row_ok(self):
        self._ok(_base("ZZV_SEL1", policy="Selected Approval Levels", levels=[_lvl(1)]))

    def test_none_with_requester_ok(self):
        self._ok(_base("ZZV_NONER", policy="None", requester=1, levels=[]))

    def test_none_without_requester_rejected(self):
        self._bad(_base("ZZV_NONE0", policy="None", requester=0, levels=[]))

    def test_requester_only_profile_ok(self):
        # requester=1, policy=None, zero rows -> valid
        self._ok(_base("ZZV_REQONLY", policy="None", requester=1, levels=[]))

    def test_legacy_blank_policy_behaves_as_selected(self):
        # policy unset -> Selected -> needs a row
        self._bad(_base("ZZV_LEG0", policy=None, levels=[]))
        self._ok(_base("ZZV_LEG1", policy=None, levels=[_lvl(1)]))

    def test_duplicate_level_still_rejected(self):
        self._bad(_base("ZZV_DUP", policy="Selected Approval Levels",
                        levels=[_lvl(1), _lvl(1)]))

    def test_deadline_validation_preserved(self):
        self._bad(_base("ZZV_DL", policy="All Approval Levels", levels=[],
                        deadline_rule="Fixed Days"))  # deadline_days missing

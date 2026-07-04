# Copyright (c) 2026, eCentric and contributors
"""Phase A (final) schema/controller tests: reusable approval engine + AI Topup.

  bench --site <site> run-tests --module \
    ecentric_workspace.approval_center.tests.test_ai_topup_schema
"""
import frappe
from frappe.tests.utils import FrappeTestCase

ENGINE = ["EC Approval Process", "EC Approval Level", "EC Approval Participant",
          "EC Approval Request", "EC Approval Request Level",
          "EC Approval Request Approver", "EC Approval Action"]
BIZ = ["EC AI Tool", "EC AI Topup Request"]
REMOVED = ["EC Approval Level Approver", "EC AI Topup Settings", "EC AI Topup Fulfiller"]
PFX = "ZZAI_"


def _proc(code, status="Draft", approval_type="AI_TOPUP"):
    n = PFX + code
    if frappe.db.exists("EC Approval Process", n):
        return frappe.get_doc("EC Approval Process", n)
    return frappe.get_doc({"doctype": "EC Approval Process", "process_code": n, "title": n,
                           "approval_type": approval_type, "status": status}).insert(ignore_permissions=True)


def _lvl(proc, level_no, mode="Any One", minc=0, approvers=None):
    d = frappe.get_doc({"doctype": "EC Approval Level", "approval_process": proc, "level_no": level_no,
                        "level_name": "L%s" % level_no, "approval_mode": mode, "minimum_approvals": minc})
    for u in (approvers or []):
        d.append("participants", {"participant_purpose": "Approver", "source_type": "User", "user": u})
    return d.insert(ignore_permissions=True)


class TestPhaseASchema(FrappeTestCase):
    def test_doctypes_exist_and_removed(self):
        for dt in ENGINE + BIZ:
            self.assertTrue(frappe.db.exists("DocType", dt), dt)
            self.assertEqual(frappe.get_meta(dt).module, "Approval Center")
        for dt in REMOVED:
            self.assertFalse(frappe.db.exists("DocType", dt), "should be removed: " + dt)

    def test_ai_topup_has_no_approval_state_fields(self):
        fns = {f.fieldname for f in frappe.get_meta("EC AI Topup Request").fields}
        self.assertNotIn("approval_status", fns)
        self.assertNotIn("current_stage", fns)
        self.assertIn("fulfillment_status", fns)

    def test_process_code_immutable(self):
        p = _proc("IMM")
        p.process_code = PFX + "IMM2"
        with self.assertRaises(frappe.exceptions.ValidationError):
            p.save(ignore_permissions=True)

    def test_one_active_per_type(self):
        _proc("A1", status="Active")
        with self.assertRaises(frappe.exceptions.ValidationError):
            frappe.get_doc({"doctype": "EC Approval Process", "process_code": PFX + "A2",
                            "title": "x", "approval_type": "AI_TOPUP", "status": "Active"}
                           ).insert(ignore_permissions=True)

    def test_duplicate_level_no_blocked(self):
        p = _proc("LV")
        _lvl(p.name, 1)
        with self.assertRaises(frappe.exceptions.ValidationError):
            _lvl(p.name, 1)

    def test_mode_validations(self):
        p = _proc("MODE")
        # Minimum Count needs min>=1
        with self.assertRaises(frappe.exceptions.ValidationError):
            _lvl(p.name, 10, mode="Minimum Count", minc=0)
        # min cannot exceed approver count
        with self.assertRaises(frappe.exceptions.ValidationError):
            _lvl(p.name, 11, mode="Minimum Count", minc=3, approvers=["Administrator"])
        # Any One / All Required reset min to 0
        self.assertEqual(_lvl(p.name, 12, mode="Any One", minc=5).minimum_approvals, 0)
        self.assertEqual(_lvl(p.name, 13, mode="All Required", minc=5).minimum_approvals, 0)
        self.assertEqual(_lvl(p.name, 14, mode="Minimum Count", minc=1, approvers=["Administrator"]).minimum_approvals, 1)

    def test_duplicate_participant_blocked(self):
        p = _proc("DUP")
        with self.assertRaises(frappe.exceptions.ValidationError):
            _lvl(p.name, 20, approvers=["Administrator", "Administrator"])

    def test_invalid_participant_source_fields(self):
        p = _proc("SRC")
        d = frappe.get_doc({"doctype": "EC Approval Level", "approval_process": p.name, "level_no": 21,
                            "level_name": "S", "approval_mode": "Any One"})
        # User source with a role populated -> invalid
        d.append("participants", {"participant_purpose": "Approver", "source_type": "User",
                                  "user": "Administrator", "role": "System Manager"})
        with self.assertRaises(frappe.exceptions.ValidationError):
            d.insert(ignore_permissions=True)

    def test_runtime_approver_duplicate_blocked(self):
        p = _proc("RT")
        req = frappe.get_doc({"doctype": "EC Approval Request", "approval_type": "AI_TOPUP",
                              "reference_doctype": "EC Approval Process", "reference_name": p.name,
                              "approval_process": p.name, "approval_status": "Pending"}).insert(ignore_permissions=True)
        rl = frappe.get_doc({"doctype": "EC Approval Request Level", "approval_request": req.name,
                             "level_no": 1, "level_name": "L1"}).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "EC Approval Request Approver", "approval_request": req.name,
                        "request_level": rl.name, "approver": "Administrator"}).insert(ignore_permissions=True)
        with self.assertRaises(frappe.exceptions.ValidationError):
            frappe.get_doc({"doctype": "EC Approval Request Approver", "approval_request": req.name,
                            "request_level": rl.name, "approver": "Administrator"}).insert(ignore_permissions=True)

    def test_snapshot_level_frozen(self):
        p = _proc("SNAP")
        req = frappe.get_doc({"doctype": "EC Approval Request", "approval_type": "AI_TOPUP",
                              "reference_doctype": "EC Approval Process", "reference_name": p.name,
                              "approval_process": p.name, "approval_status": "Pending"}).insert(ignore_permissions=True)
        rl = frappe.get_doc({"doctype": "EC Approval Request Level", "approval_request": req.name,
                             "level_no": 1, "level_name": "L1", "approval_mode": "Any One"}).insert(ignore_permissions=True)
        rl.approval_mode = "All Required"  # frozen config field
        with self.assertRaises(frappe.exceptions.ValidationError):
            rl.save(ignore_permissions=True)
        # but runtime status may change
        rl.reload()
        rl.level_status = "Approved"
        rl.save(ignore_permissions=True)

    def test_action_append_only(self):
        p = _proc("ACT")
        req = frappe.get_doc({"doctype": "EC Approval Request", "approval_type": "AI_TOPUP",
                              "reference_doctype": "EC Approval Process", "reference_name": p.name,
                              "approval_process": p.name, "approval_status": "Pending"}).insert(ignore_permissions=True)
        act = frappe.get_doc({"doctype": "EC Approval Action", "approval_request": req.name,
                              "action": "Submitted", "actor": "Administrator"}).insert(ignore_permissions=True)
        act.comment = "tamper"
        with self.assertRaises(frappe.exceptions.ValidationError):
            act.save(ignore_permissions=True)
        with self.assertRaises(frappe.exceptions.ValidationError):
            act.reload(); act.delete(ignore_permissions=True)

    def test_unique_active_request_per_document(self):
        p = _proc("UNIQ")
        frappe.get_doc({"doctype": "EC Approval Request", "approval_type": "AI_TOPUP",
                        "reference_doctype": "EC Approval Process", "reference_name": p.name,
                        "approval_process": p.name, "approval_status": "Pending"}).insert(ignore_permissions=True)
        with self.assertRaises(frappe.exceptions.ValidationError):
            frappe.get_doc({"doctype": "EC Approval Request", "approval_type": "AI_TOPUP",
                            "reference_doctype": "EC Approval Process", "reference_name": p.name,
                            "approval_process": p.name, "approval_status": "Pending"}).insert(ignore_permissions=True)

    def test_finance_comment_not_unconditional_at_doctype(self):
        # DocType must NOT block a differing approved/requested amount on plain save/submit;
        # the mandatory-comment rule lives in ai_topup.service.finance_approve (Finance action only).
        d = frappe.get_doc({"doctype": "EC AI Topup Request", "requested_amount": 100,
                            "approved_amount": 80}).insert(ignore_permissions=True)
        self.assertTrue(d.name)

    def test_completion_requires_evidence(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            frappe.get_doc({"doctype": "EC AI Topup Request", "fulfillment_status": "Completed"}
                           ).insert(ignore_permissions=True)

    def test_completed_fields_locked(self):
        r = frappe.get_doc({"doctype": "EC AI Topup Request", "fulfillment_status": "Completed",
                            "actual_account": "a", "actual_tool_package": "p", "actual_amount": 10,
                            "actual_currency": "VND", "topup_datetime": frappe.utils.now_datetime(),
                            "transaction_reference": "t", "payment_proof": "/f/p",
                            "invoice_receipt": "/f/i"}).insert(ignore_permissions=True)
        self.assertTrue(r.completed_by and r.completed_at)
        r.actual_amount = 999
        with self.assertRaises(frappe.exceptions.ValidationError):
            r.save(ignore_permissions=True)

    def test_unique_fields_are_db_unique(self):
        # DB-level guarantees (not only controller checks)
        m = frappe.get_meta("EC Approval Process").get_field("active_process_key")
        self.assertTrue(m and m.unique, "active_process_key must be a unique field")
        r = frappe.get_meta("EC Approval Request").get_field("reference_key")
        self.assertTrue(r and r.unique, "reference_key must be a unique field")

    def test_active_process_key_value(self):
        p = _proc("KEYA", status="Active")
        self.assertEqual(p.active_process_key, "AI_TOPUP")
        d = _proc("KEYD", status="Draft")
        self.assertIsNone(d.active_process_key)

    def test_new_version_active_after_retire(self):
        v1 = _proc("VER1", status="Active")
        v1.status = "Retired"
        v1.save(ignore_permissions=True)
        self.assertIsNone(v1.active_process_key)
        # a new version may now become Active for the same approval_type
        v2 = frappe.get_doc({"doctype": "EC Approval Process", "process_code": PFX + "VER2",
                             "title": "v2", "approval_type": "AI_TOPUP", "status": "Active"}
                            ).insert(ignore_permissions=True)
        self.assertEqual(v2.active_process_key, "AI_TOPUP")

    def test_reference_key_null_when_terminal_allows_new_request(self):
        p = _proc("TERM")
        r1 = frappe.get_doc({"doctype": "EC Approval Request", "approval_type": "AI_TOPUP",
                             "reference_doctype": "EC Approval Process", "reference_name": p.name,
                             "approval_process": p.name, "approval_status": "Pending"}).insert(ignore_permissions=True)
        self.assertEqual(r1.reference_key, "EC Approval Process::" + p.name)
        r1.approval_status = "Approved"
        r1.save(ignore_permissions=True)
        self.assertIsNone(r1.reference_key)  # freed
        # a new open request for the same document is now allowed
        r2 = frappe.get_doc({"doctype": "EC Approval Request", "approval_type": "AI_TOPUP",
                             "reference_doctype": "EC Approval Process", "reference_name": p.name,
                             "approval_process": p.name, "approval_status": "Pending"}).insert(ignore_permissions=True)
        self.assertEqual(r2.reference_key, "EC Approval Process::" + p.name)

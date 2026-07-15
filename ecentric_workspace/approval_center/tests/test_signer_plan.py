# Copyright (c) 2026, eCentric and contributors
"""Read-only SIGNER PLAN resolver (Phase B1). Verifies preview vs frozen resolution, the
Digital Signature Profile signing policy, Any One / All Required / Minimum Count slot
semantics, requester slot, SCTS-mapping metadata, deterministic/stable slot keys, structured
unresolved states, permission safety, and ZERO writes/side effects.

Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_signer_plan
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import payment_request as papi
from ecentric_workspace.approval_center.esign import signer_plan as sp
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

BD, AT = "EC Payment Request", "PAYMENT_REQUEST"
PROFILE = "ZZESN_PAYR"
AR = "EC Approval Request"
ARL = "EC Approval Request Level"
ARA = "EC Approval Request Approver"


def _profile(policy="All Approval Levels", requester=1):
    fx.ensure_process(); fx.ensure_settings(allowed_users=None); fx.ensure_profile()
    frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                        {"approver_signature_policy": policy, "requester_signature_required": requester})


def _keys(plan):
    return [s["slot_key"] for s in plan["slots"]]


def _level_slots(plan, level_no):
    return [s for s in plan["slots"] if s.get("level_no") == level_no]


def _set_frozen_level(ar, level_no, mode, minimum=0):
    n = frappe.get_all(ARL, filters={"approval_request": ar, "level_no": level_no}, pluck="name")[0]
    frappe.db.set_value(ARL, n, {"approval_mode": mode, "minimum_approvals": minimum})


def _add_frozen_approver(ar, level_no, user):
    rl = frappe.get_all(ARL, filters={"approval_request": ar, "level_no": level_no}, pluck="name")[0]
    frappe.get_doc({"doctype": ARA, "approval_request": ar, "request_level": rl,
                    "level_no": level_no, "approver": user, "source": "Test", "status": "Pending"}
                   ).insert(ignore_permissions=True)


class TestSignerPlan(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    # ---- resolution source ----
    def test_preview_for_unsubmitted_draft(self):
        _profile()
        h = fx.full_stack(fx.PFX + "sp1@example.com", fx.PFX + "sp1m@example.com")
        frappe.set_user(h["requester"])
        biz = fx.draft_payment_request(h["requester"])
        frappe.db.set_value(BD, biz, "approval_type", AT)
        plan = sp.resolve_signer_plan(BD, biz)
        frappe.set_user("Administrator")
        self.assertTrue(plan["resolved"])
        self.assertEqual(plan["source"], "preview")

    def test_frozen_when_approval_request_exists(self):
        _profile()
        h = fx.full_stack(fx.PFX + "sp2@example.com", fx.PFX + "sp2m@example.com")
        frappe.set_user(h["requester"])
        plan = sp.resolve_signer_plan(BD, h["biz"])
        frappe.set_user("Administrator")
        self.assertTrue(plan["resolved"])
        self.assertEqual(plan["source"], "frozen")

    # ---- requester slot + policy ----
    def test_requester_only_plan(self):
        _profile(policy="None", requester=1)
        h = fx.full_stack(fx.PFX + "sp3@example.com", fx.PFX + "sp3m@example.com")
        frappe.set_user(h["requester"])
        plan = sp.resolve_signer_plan(BD, h["biz"])
        frappe.set_user("Administrator")
        self.assertEqual(_keys(plan), ["requester"])
        self.assertEqual(plan["slots"][0]["kind"], "requester")
        self.assertEqual(plan["slots"][0]["candidates"][0]["user"], h["requester"])

    def test_requester_plus_one_level(self):
        _profile(policy="Final Approval Level Only", requester=1)
        h = fx.full_stack(fx.PFX + "sp4@example.com", fx.PFX + "sp4m@example.com")
        frappe.set_user(h["requester"])
        plan = sp.resolve_signer_plan(BD, h["biz"])
        frappe.set_user("Administrator")
        kinds = [s["kind"] for s in plan["slots"]]
        self.assertEqual(kinds.count("requester"), 1)
        self.assertEqual(kinds.count("approval_level"), 1)   # only the final level signs

    def test_profile_filters_non_signing_level(self):
        # Selected policy + a single requires_signature row -> exactly one signing level
        _profile(policy="Selected Approval Levels", requester=0)
        frappe.db.delete("EC Digital Signature Profile Level", {"parent": PROFILE})
        frappe.get_doc({"doctype": "EC Digital Signature Profile Level", "parent": PROFILE,
                        "parenttype": "EC Digital Signature Profile", "parentfield": "levels",
                        "level_no": 4, "requires_signature": 1,
                        "mandatory_placements_per_file": 1}).insert(ignore_permissions=True)
        h = fx.full_stack(fx.PFX + "sp5@example.com", fx.PFX + "sp5m@example.com")
        frappe.set_user(h["requester"])
        plan = sp.resolve_signer_plan(BD, h["biz"])
        frappe.set_user("Administrator")
        lvls = sorted({s["level_no"] for s in plan["slots"] if s["kind"] == "approval_level"})
        self.assertEqual(lvls, [4])

    # ---- Any One / All / Minimum (controlled frozen level) ----
    def test_any_one_two_candidates_one_slot(self):
        _profile(policy="All Approval Levels", requester=0)
        h = fx.full_stack(fx.PFX + "sp6@example.com", fx.PFX + "sp6m@example.com")
        _set_frozen_level(h["ar"], 2, "Any One")
        _add_frozen_approver(h["ar"], 2, fx.user(fx.PFX + "sp6b@example.com"))
        frappe.set_user(h["requester"])
        plan = sp.resolve_signer_plan(BD, h["biz"])
        frappe.set_user("Administrator")
        s2 = _level_slots(plan, 2)
        self.assertEqual(len(s2), 1)                        # ONE slot for Any One
        self.assertEqual(s2[0]["slot_key"], "L2")
        self.assertGreaterEqual(len(s2[0]["candidates"]), 2)  # pool

    def test_all_required_two_approvers_two_slots(self):
        _profile(policy="All Approval Levels", requester=0)
        h = fx.full_stack(fx.PFX + "sp7@example.com", fx.PFX + "sp7m@example.com")
        _set_frozen_level(h["ar"], 2, "All Required")
        _add_frozen_approver(h["ar"], 2, fx.user(fx.PFX + "sp7b@example.com"))
        frappe.set_user(h["requester"])
        plan = sp.resolve_signer_plan(BD, h["biz"])
        frappe.set_user("Administrator")
        s2 = _level_slots(plan, 2)
        self.assertEqual(len(s2), 2)                        # one slot per approver
        self.assertTrue(all(len(s["candidates"]) == 1 for s in s2))
        self.assertEqual(sorted(s["slot_key"] for s in s2), ["L2#0", "L2#1"])

    def test_minimum_count_capacity(self):
        _profile(policy="All Approval Levels", requester=0)
        h = fx.full_stack(fx.PFX + "sp8@example.com", fx.PFX + "sp8m@example.com")
        _set_frozen_level(h["ar"], 2, "Minimum Count", minimum=2)
        _add_frozen_approver(h["ar"], 2, fx.user(fx.PFX + "sp8b@example.com"))
        _add_frozen_approver(h["ar"], 2, fx.user(fx.PFX + "sp8c@example.com"))
        frappe.set_user(h["requester"])
        plan = sp.resolve_signer_plan(BD, h["biz"])
        frappe.set_user("Administrator")
        s2 = _level_slots(plan, 2)
        self.assertEqual(len(s2), 2)                        # minimum_approvals slots
        self.assertTrue(all(len(s["candidates"]) >= 2 for s in s2))  # shared pool, unbound

    # ---- SCTS mapping metadata ----
    def test_missing_mapping_keeps_slot(self):
        _profile(policy="None", requester=1)
        h = fx.full_stack(fx.PFX + "sp9@example.com", fx.PFX + "sp9m@example.com")
        # no verified mapping for the requester
        frappe.db.delete("EC SCTS User Mapping", {"frappe_user": h["requester"]})
        frappe.set_user(h["requester"])
        plan = sp.resolve_signer_plan(BD, h["biz"])
        frappe.set_user("Administrator")
        self.assertEqual(_keys(plan), ["requester"])        # slot still present
        self.assertEqual(plan["slots"][0]["candidates"][0]["scts_mapping_status"], "missing")

    # ---- stability ----
    def test_repeated_calls_stable_keys(self):
        _profile()
        h = fx.full_stack(fx.PFX + "sp10@example.com", fx.PFX + "sp10m@example.com")
        frappe.set_user(h["requester"])
        a = sp.resolve_signer_plan(BD, h["biz"])
        b = sp.resolve_signer_plan(BD, h["biz"])
        frappe.set_user("Administrator")
        self.assertEqual(_keys(a), _keys(b))

    def test_preview_and_frozen_keys_stable_for_unchanged_process(self):
        _profile()
        h = fx.full_stack(fx.PFX + "sp11@example.com", fx.PFX + "sp11m@example.com")
        # frozen plan for the submitted request
        frozen = sp.resolve_signer_plan(BD, h["biz"])
        # a second (unsubmitted) request by the same requester on the SAME process
        biz2 = fx.draft_payment_request(h["requester"])
        frappe.db.set_value(BD, biz2, "approval_type", AT)
        preview = sp.resolve_signer_plan(BD, biz2)
        frappe.set_user("Administrator")
        self.assertEqual(preview["source"], "preview")
        self.assertEqual(frozen["source"], "frozen")
        self.assertEqual(_keys(preview), _keys(frozen))     # identical slot keys, unchanged process

    # ---- unresolved / permission / no-writes ----
    def test_incomplete_draft_returns_unresolved(self):
        _profile()
        owner = fx.user(fx.PFX + "sp12@example.com")
        frappe.set_user(owner)
        biz = fx.draft_payment_request(owner)
        frappe.db.set_value(BD, biz, "approval_type", None)   # no type resolvable
        # remove enabled profiles for the doctype so preview cannot infer a type
        plan = sp.resolve_signer_plan(BD, biz)
        frappe.set_user("Administrator")
        self.assertFalse(plan["resolved"])
        self.assertIn(plan["reason"],
                      ("process_not_resolved", "profile_not_configured",
                       "ambiguous_profile", "approval_type_missing", "approvers_unresolved"))

    def test_unauthorized_user_denied(self):
        _profile()
        h = fx.full_stack(fx.PFX + "sp13@example.com", fx.PFX + "sp13m@example.com")
        stranger = fx.user(fx.PFX + "sp13x@example.com")
        frappe.set_user(stranger)
        with self.assertRaises(frappe.PermissionError):
            sp.resolve_signer_plan(BD, h["biz"])
        frappe.set_user("Administrator")

    def test_no_writes_or_side_effects(self):
        _profile()
        h = fx.full_stack(fx.PFX + "sp14@example.com", fx.PFX + "sp14m@example.com")
        counts = {dt: frappe.db.count(dt) for dt in
                  (AR, "EC Digital Signature Package", "EC Digital Signature Request",
                   "EC Digital Signature Placement", "ToDo", ARA)}
        frappe.set_user(h["requester"])
        sp.resolve_signer_plan(BD, h["biz"])
        sp.resolve_signer_plan(BD, h["biz"])     # repeated -> still side-effect free
        frappe.set_user("Administrator")
        for dt, before in counts.items():
            self.assertEqual(frappe.db.count(dt), before, "resolver mutated %s" % dt)

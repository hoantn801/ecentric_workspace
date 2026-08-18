# Copyright (c) 2026, eCentric and contributors
"""PURE tests (no frappe, no DB): keeps flow.payment_request honest against esign.state
and against the EC Digital Signature Profile doctype's own declared options - the two
things it claims to describe. If either drifts, this test is what should fail, not a
production incident.
Runnable anywhere: python -m unittest ecentric_workspace.approval_center.tests.test_esign_flow_contract
"""
import json
import os
import unittest

from ecentric_workspace.approval_center.esign import state as sm
from ecentric_workspace.approval_center.esign.flow import resolve
from ecentric_workspace.approval_center.esign.flow.payment_request import (
    EXPECTED_PROFILE_POLICY, STEPS,
)

_APPROVAL_CENTER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _reachable(transitions, start, end):
    """BFS over a state.py transition table: is `end` reachable from `start` through
    only legal edges (0 or more hops)? A step may span several real esign.state
    transitions (e.g. requester_sign covers Draft..Approval Completed with `verify` as
    a nested step in between) - what must hold is that no illegal edge is required to
    get there, not that it's a single hop."""
    if start == end:
        return True
    seen, queue = {start}, [start]
    while queue:
        cur = queue.pop()
        for nxt in transitions.get(cur, ()):
            if nxt == end:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def _profile_field_options(fieldname):
    path = os.path.join(_APPROVAL_CENTER, "doctype", "ec_digital_signature_profile",
                        "ec_digital_signature_profile.json")
    with open(path, encoding="utf-8") as fh:
        meta = json.load(fh)
    for f in meta["fields"]:
        if f["fieldname"] == fieldname:
            return set((f.get("options") or "").split("\n"))
    raise AssertionError("field %r not found on EC Digital Signature Profile" % fieldname)


class TestFlowStepsMatchStateMachine(unittest.TestCase):
    """Every package_entry/exit and dsr_entry/exit pair a step declares must be REACHABLE
    through esign.state's own transition graph - a step may bundle several real
    transitions (e.g. requester_sign spans Draft..Approval Completed with `verify` nested
    inside it), but never a hop that graph does not allow. Every 'park' status must be a
    real PACKAGE or DSR status."""

    def test_package_edges_are_real(self):
        for s in STEPS:
            if s.package_entry is None or s.package_exit is None:
                continue
            for entry in s.package_entry:
                if entry is None:
                    continue
                self.assertIn(entry, sm.PACKAGE_STATES, "%s: unknown package_entry" % s.id)
                self.assertIn(s.package_exit, sm.PACKAGE_STATES, "%s: unknown package_exit" % s.id)
                self.assertTrue(_reachable(sm.PACKAGE_TRANSITIONS, entry, s.package_exit),
                                "%s: package %s -> %s has no legal esign.state path"
                                % (s.id, entry, s.package_exit))

    def test_dsr_edges_are_real(self):
        for s in STEPS:
            if s.dsr_entry is None or s.dsr_exit is None:
                continue
            for entry in s.dsr_entry:
                self.assertIn(entry, sm.DSR_STATES, "%s: unknown dsr_entry" % s.id)
                self.assertIn(s.dsr_exit, sm.DSR_STATES, "%s: unknown dsr_exit" % s.id)
                self.assertTrue(_reachable(sm.DSR_TRANSITIONS, entry, s.dsr_exit),
                                "%s: dsr %s -> %s has no legal esign.state path"
                                % (s.id, entry, s.dsr_exit))

    def test_park_statuses_are_real(self):
        known = set(sm.PACKAGE_STATES) | set(sm.DSR_STATES)
        for s in STEPS:
            for p in s.park:
                self.assertIn(p, known, "%s: park status %r is not a real esign.state status"
                              % (s.id, p))

    def test_step_ids_are_unique(self):
        ids = [s.id for s in STEPS]
        self.assertEqual(len(ids), len(set(ids)))


class TestExpectedProfilePolicyIsValid(unittest.TestCase):
    """EXPECTED_PROFILE_POLICY values must be options the doctype actually allows -
    otherwise drift.check() would be comparing against a value that could never occur."""

    def test_approver_signature_policy_is_a_declared_option(self):
        self.assertIn(EXPECTED_PROFILE_POLICY["approver_signature_policy"],
                      _profile_field_options("approver_signature_policy"))

    def test_provider_creation_trigger_is_a_declared_option(self):
        self.assertIn(EXPECTED_PROFILE_POLICY["provider_creation_trigger"],
                      _profile_field_options("provider_creation_trigger"))

    def test_requester_signature_required_is_boolean_like(self):
        self.assertIn(EXPECTED_PROFILE_POLICY["requester_signature_required"], (0, 1))


class TestResolveCurrentStep(unittest.TestCase):
    def test_dsr_status_requires_actor_type(self):
        with self.assertRaises(ValueError):
            resolve.current_step(dsr_status="Draft")

    def test_requester_and_approver_share_states_but_resolve_differently(self):
        r = resolve.current_step(dsr_status="Draft", dsr_actor_type="Requester")
        a = resolve.current_step(dsr_status="Draft", dsr_actor_type="Approver")
        self.assertEqual(r["step"].id, "requester_sign")
        self.assertEqual(a["step"].id, "approver_sign")
        self.assertFalse(r["parked"])
        self.assertFalse(a["parked"])

    def test_live_dsr_states_resolve_to_verify(self):
        for st in ("Queued", "Provider Accepted", "Verifying", "Signed"):
            out = resolve.current_step(dsr_status=st, dsr_actor_type="Approver")
            self.assertEqual(out["step"].id, "verify", st)
            self.assertFalse(out["parked"], st)

    def test_park_states_are_flagged_parked(self):
        for st in ("Mapping Required", "Placement Required", "Retryable Failure",
                  "Permanent Failure", "Verification Mismatch", "Manual Review"):
            out = resolve.current_step(dsr_status=st, dsr_actor_type="Approver")
            self.assertTrue(out["parked"], st)
            self.assertEqual(out["reason"], st)

    def test_approval_completed_resolves_to_owning_step(self):
        out = resolve.current_step(dsr_status="Approval Completed", dsr_actor_type="Requester")
        self.assertEqual(out["step"].id, "requester_sign")
        self.assertFalse(out["parked"])

    def test_package_only_active_resolves_to_retrieve_signed(self):
        out = resolve.current_step(package_status="Active")
        self.assertEqual(out["step"].id, "retrieve_signed")

    def test_package_provider_create_failed_is_parked(self):
        out = resolve.current_step(package_status="Provider Create Failed")
        self.assertEqual(out["step"].id, "provider_create")
        self.assertTrue(out["parked"])

    def test_no_status_defaults_to_document_setup(self):
        out = resolve.current_step()
        self.assertEqual(out["step"].id, "document_setup")
        self.assertFalse(out["parked"])


if __name__ == "__main__":
    unittest.main()

# Copyright (c) 2026, eCentric and contributors
"""Consistency guard: every governed event type emitted by the e-sign modules must be a
valid EC Digital Signature Event.event_type Select option. Fails if code emits a type
absent from the DocType (the exact class of bug the branch just fixed).

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_event_type_consistency
"""
import ast
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import state as sm


def _emitted_event_types():
    """Static inventory of event_type string literals emitted across esign/*.py:
    events.emit("X", ...), set_dsr_status(..., event_type="X"),
    set_package_status(..., event_type="X"); PLUS the state-name defaults used when
    set_dsr_status / set_package_status omit event_type (to_status.replace(' ', ''))."""
    import ecentric_workspace.approval_center.esign as pkg
    base = os.path.dirname(pkg.__file__)
    literals = set()
    for root, _dirs, files in os.walk(base):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            tree = ast.parse(open(os.path.join(root, fn), encoding="utf-8").read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fname = getattr(node.func, "attr", None)
                if fname == "emit" and node.args and isinstance(node.args[0], ast.Constant) \
                        and isinstance(node.args[0].value, str):
                    literals.add(node.args[0].value)
                if fname in ("set_dsr_status", "set_package_status"):
                    for kw in node.keywords:
                        if kw.arg == "event_type" and isinstance(kw.value, ast.Constant) \
                                and isinstance(kw.value.value, str):
                            literals.add(kw.value.value)
    # state-name defaults (event_type defaults to to_status.replace(" ", ""))
    for s in list(sm.DSR_STATES) + list(sm.PACKAGE_STATES):
        literals.add(s.replace(" ", ""))
    return literals


class TestEventTypeConsistency(FrappeTestCase):
    def test_all_emitted_event_types_are_valid_options(self):
        meta = frappe.get_meta("EC Digital Signature Event")
        options = set((meta.get_field("event_type").options or "").split("\n"))
        emitted = _emitted_event_types()
        missing = sorted(e for e in emitted if e and e not in options)
        self.assertEqual(missing, [], "event types emitted but missing from the Select: %s"
                         % missing)

    def test_new_and_prior_event_types_present(self):
        meta = frappe.get_meta("EC Digital Signature Event")
        options = set((meta.get_field("event_type").options or "").split("\n"))
        required = [
            "SignedFileRetrievalStarted", "SignedFileRetrieved", "SignedFileStored",
            "SignedFileDuplicateSkipped", "SignedFileHashMismatch", "SignedFileRetrievalFailed",
            "BindingValidated", "BindingRejected", "SignatureOwnershipValidated",
            "SignatureOwnershipRejected", "BulkOutcomeUnknown", "CreateOutcomeUnknown",
            "CreateReconciled", "CreateReconcileRejected"]
        for r in required:
            self.assertIn(r, options, "%s must be a valid event_type option" % r)

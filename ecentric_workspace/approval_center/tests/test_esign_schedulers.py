# Copyright (c) 2026, eCentric and contributors
"""E-sign scheduler wiring + safety (release fix). Proves hooks register each governed
task exactly once, gates OFF -> zero adapter/network, polling only processes eligible
non-terminal DSRs, signed-file retry never resends AddDocument/bulk-process, and repeated
invocation is idempotent.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_schedulers
"""
import hashlib
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import orchestrator, service as esvc, tasks
from ecentric_workspace.approval_center.esign import signed_files
from ecentric_workspace.approval_center.esign.providers.base import NormalizedDocState
from ecentric_workspace.approval_center.tests import esign_fixtures as fx
from ecentric_workspace.approval_center.tests.test_scts_orchestration import (
    _scts_stack, _transport, _AdapterFactory)

DSR = "EC Digital Signature Request"
PKG = "EC Digital Signature Package"
SETTINGS = "EC Digital Signature Provider Settings"


def _settings_name():
    return frappe.db.get_value(SETTINGS, {"provider": "SCTS", "environment": "UAT"}, "name")


class _SignedSpy(object):
    def __init__(self):
        self.writes = {"create": 0, "bulk": 0}

    def poll_status(self, document_id):
        return NormalizedDocState(document_id, "signed",
                                  signers=[{"user_id": "U", "status": "signed"}],
                                  files=[{"file_id": "F0"}])

    def get_signed_document(self, document_id, file_id=None):
        b = b"%PDF-1.4 signed\n%%EOF"
        return {"content": b, "sha256": hashlib.sha256(b).hexdigest(), "size": len(b)}

    def create_document(self, ctx):
        self.writes["create"] += 1
        return {"document_id": "x", "files": []}

    def approve_and_sign(self, *a, **k):
        self.writes["bulk"] += 1
        return {"bulk_job_transaction_id": "x"}


class TestEsignSchedulers(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def _queued(self, h):
        frappe.set_user(h["mgr"])
        res = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        return res["signature_request"]

    def _complete(self, h):
        dsr = self._queued(h)
        with patch.object(tasks, "get_adapter", _AdapterFactory(_transport())):
            orchestrator.submit_provider_request(dsr)
        return dsr

    # ---- hooks: each task exactly once ----
    def test_hooks_register_each_esign_task_exactly_once(self):
        sched = frappe.get_hooks("scheduler_events")
        flat = []

        def walk(x):
            if isinstance(x, str):
                flat.append(x)
            elif isinstance(x, (list, tuple)):
                for i in x:
                    walk(i)
            elif isinstance(x, dict):
                for v in x.values():
                    walk(v)

        walk(sched)
        for t in ("poll_pending", "sweep_stale", "orphan_file_scan", "retrieve_signed_bundles"):
            path = "ecentric_workspace.approval_center.esign.tasks." + t
            self.assertEqual(flat.count(path), 1, "%s registered %d times" % (t, flat.count(path)))

    # ---- gates OFF -> zero adapter / network ----
    def test_poll_pending_gate_off_builds_no_adapter(self):
        h = _scts_stack("s1r", "s1m")
        dsr = self._queued(h)
        frappe.db.set_value(SETTINGS, _settings_name(), "integration_enabled", 0)

        def spy(settings):
            raise AssertionError("no adapter may be built while integration is OFF")

        with patch.object(tasks, "get_adapter", spy):
            tasks.poll_pending()
        self.assertEqual(frappe.db.get_value(DSR, dsr, "status"), "Queued")  # untouched

    def test_retrieve_gate_off_builds_no_adapter(self):
        h = _scts_stack("s2r", "s2m")
        frappe.db.set_value(PKG, h["pkg"], "signed_bundle_complete", 0)
        frappe.db.set_value(SETTINGS, _settings_name(), "integration_enabled", 0)

        def spy(settings):
            raise AssertionError("no adapter may be built while integration is OFF")

        with patch.object(signed_files, "get_adapter", spy):
            tasks.retrieve_signed_bundles()  # gate OFF -> skipped, no adapter

    # ---- polling only touches eligible non-terminal DSRs ----
    def test_poll_pending_skips_terminal_dsr(self):
        h = _scts_stack("s3r", "s3m")
        dsr = self._complete(h)  # -> Approval Completed (terminal)
        self.assertEqual(frappe.db.get_value(DSR, dsr, "status"), "Approval Completed")
        with patch.object(tasks, "process_signing_request") as proc:
            tasks.poll_pending()
        self.assertEqual(proc.call_count, 0)  # terminal DSR never reprocessed

    # ---- signed-file retry never resends writes ----
    def test_retrieve_never_resends_add_or_bulk(self):
        h = _scts_stack("s4r", "s4m")
        self._complete(h)
        frappe.db.set_value(PKG, h["pkg"], "signed_bundle_complete", 0)
        spy = _SignedSpy()
        with patch.object(signed_files, "get_adapter", lambda s: spy):
            tasks.retrieve_signed_bundles()
        self.assertEqual(spy.writes, {"create": 0, "bulk": 0})  # only safe reads

    # ---- idempotent double invocation ----
    def test_poll_pending_idempotent(self):
        h = _scts_stack("s5r", "s5m")
        dsr = self._complete(h)
        with patch.object(tasks, "get_adapter", _AdapterFactory(_transport())):
            tasks.poll_pending()
            tasks.poll_pending()
        self.assertEqual(frappe.db.get_value(DSR, dsr, "status"), "Approval Completed")
        self.assertEqual(frappe.db.count("EC Approval Action",
                                         {"approval_request": h["ar"], "action": "Approved"}), 1)

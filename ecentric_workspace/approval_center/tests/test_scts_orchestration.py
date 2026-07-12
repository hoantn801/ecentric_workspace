# Copyright (c) 2026, eCentric and contributors
"""SCTS provider orchestration (submit_provider_request / poll_provider_request) driven
end-to-end through the real worker with a fake SCTS transport (no network). Proves:
  * a verified provider Document status is REQUIRED before engine completion;
  * the Approval Engine completes exactly once (one Approved action, one level advance,
    no duplicate ToDo);
  * duplicate submit yields a single bulk-process write (poll-first idempotency);
  * an ambiguous provider result never completes and never downgrades a terminal state;
  * normal approve stays blocked at a signing-required level.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_scts_orchestration
"""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import service as engine
from ecentric_workspace.approval_center.esign import orchestrator, service as esvc, tasks
from ecentric_workspace.approval_center.tests import esign_fixtures as fx
from ecentric_workspace.approval_center.tests import scts_fixtures as sx

DSR = "EC Digital Signature Request"
DOC_ID = "SCTS-DOC-1"


def _scts_settings():
    name = frappe.db.get_value("EC Digital Signature Provider Settings",
                               {"provider": "SCTS", "environment": "UAT"}, "name")
    vals = {"base_url": "https://scts.uat.local", "username": "erp-bot",
            "integration_enabled": 1, "allow_document_creation": 1, "allow_signing": 1,
            "allow_production_signing": 0}
    if name:
        doc = frappe.get_doc("EC Digital Signature Provider Settings", name)
        doc.update(vals)
        doc.save(ignore_permissions=True)
        return name
    return frappe.get_doc(dict({"doctype": "EC Digital Signature Provider Settings",
                                "provider": "SCTS", "environment": "UAT"}, **vals)
                          ).insert(ignore_permissions=True).name


def _scts_stack(reqmail, mgrmail):
    """fx.full_stack, flipped to the SCTS provider with a preset provider document id."""
    h = fx.full_stack(fx.PFX + reqmail, fx.PFX + mgrmail)
    sname = _scts_settings()
    frappe.db.set_value("EC Digital Signature Provider Settings", sname,
                        "allowed_signing_users", "\n".join(h["approvers"]))
    frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR", "provider", "SCTS")
    frappe.db.set_value("EC Digital Signature Package", h["pkg"], "scts_document_id", DOC_ID)
    return h


def _transport(sign_after_submit=True, signer_status="signed"):
    """Fake SCTS transport: signatures owned+active for any queried user; bulk-process
    accepted; Document shows the submitted signer only AFTER bulk-process (poll-first)."""
    state = {"submitted": False, "user": None, "sig": None}

    def sigs(req):
        uid = req["url"].rsplit("/", 1)[-1]
        return sx.FakeResponse(200, [{"id": "SIG-" + uid, "signerId": uid, "isActive": True}])

    def bulk(req):
        b = req["body"]
        state.update(submitted=True, user=b["userId"], sig=b["signatureId"])
        return sx.bulk_ok("TXN-1")

    def doc(req):
        signers = []
        if state["submitted"] and sign_after_submit:
            signers = [{"userId": state["user"], "signatureId": state["sig"],
                        "status": signer_status, "signedAt": "2026-07-12T09:00:00"}]
        return sx.FakeResponse(200, {"id": DOC_ID, "status": "in_progress", "signers": signers,
                                     "files": [{"documentFileId": "F0"}, {"documentFileId": "F1"}]})

    return sx.FakeTransport({"get_signatures": sigs, "bulk_process": bulk, "get_document": doc})


class _AdapterFactory(object):
    """Patches tasks.get_adapter to return SCTS adapters over a shared fake transport,
    with frappe credential/token I/O stubbed. Records every adapter's transport."""

    def __init__(self, transport):
        self.transport = transport
        self.built = 0

    def __call__(self, settings):
        from ecentric_workspace.approval_center.esign.providers.scts import SctsAdapter
        ad = SctsAdapter(settings, transport=self.transport, sleeper=lambda *_: None)
        ad._cached_token = lambda: "tok"
        ad._password = lambda f: "tok" if f == "token_cache" else "pw"
        ad._store_token = lambda *a, **k: None
        self.built += 1
        return ad


class TestSctsOrchestration(FrappeTestCase):
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

    def test_submit_then_poll_completes_exactly_once(self):
        h = _scts_stack("o1r", "o1m")
        dsr = self._queued(h)
        t = _transport()
        with patch.object(tasks, "get_adapter", _AdapterFactory(t)):
            out = orchestrator.submit_provider_request(dsr)
        self.assertTrue(out["submitted"])
        self.assertEqual(frappe.db.get_value(DSR, dsr, "status"), "Approval Completed")
        self.assertEqual(t.count("bulk_process"), 1)
        # engine completed exactly once, level advanced, single Approved action
        self.assertEqual(frappe.db.count("EC Approval Action",
                                         {"approval_request": h["ar"], "action": "Approved"}), 1)
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 2)
        # exactly one open ToDo for the next level (no duplicate handoff)
        self.assertEqual(frappe.db.count("ToDo", {"reference_type": "EC Payment Request",
                                                  "reference_name": h["biz"], "status": "Open"}), 1)

    def test_duplicate_submit_single_bulk_process(self):
        h = _scts_stack("o2r", "o2m")
        dsr = self._queued(h)
        t = _transport()
        fac = _AdapterFactory(t)
        with patch.object(tasks, "get_adapter", fac):
            orchestrator.submit_provider_request(dsr)
            second = orchestrator.submit_provider_request(dsr)  # DSR already terminal
        self.assertFalse(second["submitted"])
        self.assertEqual(t.count("bulk_process"), 1)  # never re-submitted

    def test_repoll_terminal_is_idempotent_no_downgrade(self):
        h = _scts_stack("o3r", "o3m")
        dsr = self._queued(h)
        t = _transport()
        with patch.object(tasks, "get_adapter", _AdapterFactory(t)):
            orchestrator.submit_provider_request(dsr)
            out = orchestrator.poll_provider_request(dsr)
        self.assertFalse(out["polled"])
        self.assertEqual(out["status"], "Approval Completed")  # never downgraded
        self.assertEqual(frappe.db.count("EC Approval Action",
                                         {"approval_request": h["ar"], "action": "Approved"}), 1)

    def test_ambiguous_result_never_completes(self):
        h = _scts_stack("o4r", "o4m")
        dsr = self._queued(h)
        t = _transport(signer_status="pending")  # accepted, but never verified signed
        with patch.object(tasks, "get_adapter", _AdapterFactory(t)):
            orchestrator.submit_provider_request(dsr)
        self.assertIn(frappe.db.get_value(DSR, dsr, "status"),
                      ("Provider Accepted", "Verifying"))
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 1)  # NOT advanced
        self.assertEqual(frappe.db.count("EC Approval Action",
                                         {"approval_request": h["ar"], "action": "Approved"}), 0)

    def test_normal_approve_blocked_at_signing_level(self):
        h = _scts_stack("o5r", "o5m")
        frappe.set_user(h["mgr"])
        with self.assertRaises(frappe.PermissionError):
            engine.approve(h["ar"], actor=h["mgr"], comment="plain approve")
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 1)

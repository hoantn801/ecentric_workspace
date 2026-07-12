# Copyright (c) 2026, eCentric and contributors
"""Payment Request end-to-end signing (S2B-B): governed placement geometry, ambiguous
AddDocument protection (no auto-recreate + reconcile), and approve-and-sign governance.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_pr_e2e_signing
"""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import service as engine
from ecentric_workspace.approval_center.esign import package as pkgsvc, service as esvc, tasks
from ecentric_workspace.approval_center.esign import api as esign_api
from ecentric_workspace.approval_center.tests import esign_fixtures as fx
from ecentric_workspace.approval_center.tests import scts_fixtures as sx

DSR = "EC Digital Signature Request"
PKG = "EC Digital Signature Package"


def _draft_with_signable(reqmail):
    fx.ensure_process()
    fx.ensure_settings(allowed_users=[fx.FIN])
    fx.ensure_profile()
    req = fx.user(fx.PFX + reqmail)
    biz = fx.draft_payment_request(req)
    frappe.set_user(req)
    profile = frappe.db.get_value("EC Digital Signature Profile", "ZZESN_PAYR", "name")
    pkg = pkgsvc.get_or_create_draft("EC Payment Request", biz, profile)
    dsf = pkgsvc.add_file(pkg.name, "sign.pdf", fx.PDF, requires_signature=1)
    frappe.set_user("Administrator")
    return biz, pkg.name, dsf.name


def _pl(dsf, **over):
    p = {"signature_file": dsf, "page_index": 1, "x": 50, "y": 50, "width": 120,
         "height": 40, "level_no": 1, "signature_type": "scts"}
    p.update(over)
    return [p]


class TestPlacementGeometry(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_valid_placement_accepted(self):
        biz, pkg, dsf = _draft_with_signable("g1@example.com")
        self.assertEqual(pkgsvc.save_placements(pkg, _pl(dsf)), 1)

    def test_page_zero_blocked(self):
        biz, pkg, dsf = _draft_with_signable("g2@example.com")
        with self.assertRaises(frappe.ValidationError):
            pkgsvc.save_placements(pkg, _pl(dsf, page_index=0))

    def test_page_beyond_count_blocked(self):
        biz, pkg, dsf = _draft_with_signable("g3@example.com")
        with self.assertRaises(frappe.ValidationError):
            pkgsvc.save_placements(pkg, _pl(dsf, page_index=9))

    def test_negative_coordinate_blocked(self):
        biz, pkg, dsf = _draft_with_signable("g4@example.com")
        with self.assertRaises(frappe.ValidationError):
            pkgsvc.save_placements(pkg, _pl(dsf, x=-5))

    def test_out_of_bounds_blocked(self):
        biz, pkg, dsf = _draft_with_signable("g5@example.com")
        with self.assertRaises(frappe.ValidationError):
            pkgsvc.save_placements(pkg, _pl(dsf, x=600, width=120))  # 612pt-wide page

    def test_nonpositive_size_blocked(self):
        biz, pkg, dsf = _draft_with_signable("g6@example.com")
        with self.assertRaises(frappe.ValidationError):
            pkgsvc.save_placements(pkg, _pl(dsf, width=0))

    def test_page_geometry_endpoint(self):
        biz, pkg, dsf = _draft_with_signable("g7@example.com")
        geo = pkgsvc.pdf_page_geometry(dsf)
        self.assertEqual(geo["page_count"], 1)
        self.assertEqual(geo["pages"][0]["width"], 612.0)


class _Fac(object):
    def __init__(self, transport):
        self.transport = transport

    def __call__(self, settings):
        from ecentric_workspace.approval_center.esign.providers.scts import SctsAdapter
        ad = SctsAdapter(settings, transport=self.transport, sleeper=lambda *_: None)
        ad._cached_token = lambda: "tok"
        ad._password = lambda f: "tok" if f == "token_cache" else "pw"
        ad._store_token = lambda *a, **k: None
        return ad


def _sigs(req):
    uid = req["url"].rsplit("/", 1)[-1]
    return sx.FakeResponse(200, [{"id": "SIG-" + uid, "signerId": uid, "isActive": True}])


def _e2e_transport(add_lost=True, doc_id="SCTS-DOC-REAL"):
    """SCTS transport for the ambiguous-create continuation. AddDocument is accepted
    provider-side but (optionally) the response is lost; GET Document returns a 2-file
    document (matching the package) and shows the signer signed only AFTER bulk-process."""
    state = {"bulk": False, "user": None, "sig": None}

    def add_doc(req):
        if add_lost:
            raise ConnectionError("AddDocument accepted, response lost")
        return sx.add_document_ok(doc_id, 2)

    def bulk(req):
        b = req["body"]
        state.update(bulk=True, user=b["userId"], sig=b["SignerSignatureId"])
        return sx.bulk_ok("TXN-1")

    def doc(req):
        signers = []
        if state["bulk"]:
            signers = [{"userId": state["user"], "signatureId": state["sig"],
                        "status": "signed", "signedAt": "2026-07-12T09:00:00"}]
        return sx.FakeResponse(200, {"id": doc_id, "status": "in_progress", "signers": signers,
                                     "files": [{"documentFileId": "F0"}, {"documentFileId": "F1"}]})

    return sx.FakeTransport({"get_signatures": _sigs, "add_document": add_doc,
                             "bulk_process": bulk, "get_document": doc})


class TestPrE2ESigning(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def _scts_stack(self, reqmail, mgrmail, preset_doc=False):
        h = fx.full_stack(fx.PFX + reqmail, fx.PFX + mgrmail)
        name = frappe.db.get_value("EC Digital Signature Provider Settings",
                                   {"provider": "SCTS", "environment": "UAT"}, "name")
        vals = {"base_url": "https://scts.uat.local", "username": "erp-bot",
                "integration_enabled": 1, "allow_document_creation": 1, "allow_signing": 1,
                "allow_production_signing": 0,
                "allowed_signing_users": "\n".join(h["approvers"])}
        if name:
            doc = frappe.get_doc("EC Digital Signature Provider Settings", name)
            doc.update(vals)
            doc.save(ignore_permissions=True)
        else:
            frappe.get_doc(dict({"doctype": "EC Digital Signature Provider Settings",
                                 "provider": "SCTS", "environment": "UAT"}, **vals)
                           ).insert(ignore_permissions=True)
        frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR", "provider", "SCTS")
        if preset_doc:
            frappe.db.set_value(PKG, h["pkg"], "scts_document_id", "SCTS-DOC-1")
        return h

    def _queued(self, h):
        frappe.set_user(h["mgr"])
        res = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        return res["signature_request"]

    # ---- governance ----
    def test_normal_approve_blocked_at_signing_level_all_roles(self):
        h = self._scts_stack("p1r", "p1m")
        frappe.set_user(h["mgr"])
        with self.assertRaises(frappe.PermissionError):
            engine.approve(h["ar"], actor=h["mgr"], comment="plain")
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            engine.approve(h["ar"], actor="Administrator", comment="admin plain")
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 1)

    def test_pr_approve_and_sign_non_approver_blocked(self):
        h = self._scts_stack("p2r", "p2m")
        frappe.set_user(fx.FIN)  # a level-2 approver, not the current (level-1) approver
        with self.assertRaises(frappe.PermissionError):
            esign_api.pr_approve_and_sign(h["biz"])
        frappe.set_user("Administrator")

    # ---- transitionType contract ----
    def test_bulk_transition_type_is_approve(self):
        h = self._scts_stack("p4r", "p4m", preset_doc=True)
        dsr = self._queued(h)
        t = _e2e_transport(add_lost=False, doc_id="SCTS-DOC-1")
        with patch.object(tasks, "get_adapter", _Fac(t)):
            tasks.process_signing_request(dsr)
        body = t.last_body("bulk_process")
        self.assertEqual(body["transitionType"], "approve")  # server-derived, never numeric
        self.assertNotIsInstance(body["transitionType"], int)
        self.assertEqual(frappe.db.get_value(DSR, dsr, "status"), "Approval Completed")

    # ---- ambiguous AddDocument: verified reconciliation + exactly-once continuation ----
    def test_ambiguous_create_e2e_reconcile_then_single_bulk_completes_once(self):
        h = self._scts_stack("p3r", "p3m", preset_doc=False)
        dsr = self._queued(h)
        t = _e2e_transport(add_lost=True)
        fac = _Fac(t)
        with patch.object(tasks, "get_adapter", fac), patch.object(esvc, "get_adapter", fac):
            # 1) AddDocument accepted provider-side but response lost -> exactly one call
            tasks.process_signing_request(dsr)
            self.assertEqual(t.count("add_document"), 1)
            self.assertEqual(frappe.db.get_value(PKG, h["pkg"], "error_code"),
                             "create_outcome_unknown")
            self.assertEqual(frappe.db.get_value(DSR, dsr, "status"), "Verifying")
            # a run before reconciliation must NOT recreate
            tasks.process_signing_request(dsr)
            self.assertEqual(t.count("add_document"), 1)
            # 2) governed reconciliation VERIFIES via GET /api/Document/{id}, binds, requeues
            out = esvc.reconcile_document_creation(h["pkg"], "SCTS-DOC-REAL")
            self.assertTrue(out["reconciled"])
            self.assertIsNone(frappe.db.get_value(PKG, h["pkg"], "error_code"))
            self.assertEqual(frappe.db.get_value(PKG, h["pkg"], "scts_document_id"),
                             "SCTS-DOC-REAL")
            # 3) continuation: worker submits bulk-process exactly once, polling completes
            tasks.process_signing_request(dsr)
        self.assertEqual(t.count("add_document"), 1)   # never recreated
        self.assertEqual(t.count("bulk_process"), 1)   # exactly one signing submission
        self.assertEqual(frappe.db.get_value(DSR, dsr, "status"), "Approval Completed")
        self.assertEqual(frappe.db.count("EC Approval Action",
                                         {"approval_request": h["ar"], "action": "Approved"}), 1)
        self.assertEqual(frappe.db.get_value("EC Approval Request", h["ar"],
                                             "current_level"), 2)

    def test_reconcile_rejects_unverifiable_document(self):
        h = self._scts_stack("p5r", "p5m", preset_doc=False)
        dsr = self._queued(h)
        t = _e2e_transport(add_lost=True)
        fac = _Fac(t)
        with patch.object(tasks, "get_adapter", fac), patch.object(esvc, "get_adapter", fac):
            tasks.process_signing_request(dsr)  # -> create_outcome_unknown
            # wrong id: GET /api/Document returns SCTS-DOC-REAL, not the entered id
            with self.assertRaises(frappe.ValidationError):
                esvc.reconcile_document_creation(h["pkg"], "SCTS-DOC-WRONG")
        self.assertEqual(frappe.db.get_value(PKG, h["pkg"], "error_code"),
                         "create_outcome_unknown")  # still blocked

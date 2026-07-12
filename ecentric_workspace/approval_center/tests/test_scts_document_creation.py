# Copyright (c) 2026, eCentric and contributors
"""SCTS AddDocument (S2B-B): client single-attempt ambiguity + adapter base64 payload and
response normalization. Pure, mocked transport - no network.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_scts_document_creation
"""
import base64

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign.providers.base import ProviderError
from ecentric_workspace.approval_center.esign.providers.scts_client import SctsClient
from ecentric_workspace.approval_center.tests import scts_fixtures as sx


def _client(script, retry_limit=3):
    t = sx.FakeTransport(script)
    return SctsClient("https://scts.uat.local", timeout=5, retry_limit=retry_limit,
                      transport=t, sleeper=lambda *_: None), t


def _adapter(script):
    t = sx.FakeTransport(script)
    ad = sx.make_adapter(t)
    ad._password = lambda f: {"password": "pw", "token_cache": "tok"}.get(f)
    ad._store_token = lambda *a, **k: None
    ad._cached_token = lambda: "tok"
    return ad, t


class TestSctsDocumentCreation(FrappeTestCase):
    # -- client: single attempt, ambiguous on network/5xx --
    def test_add_document_ok_single_call(self):
        c, t = _client({"add_document": sx.add_document_ok("D-1", 1)})
        r = c.add_document({"docCode": "X"}, "tok")
        self.assertEqual(r["documentId"], "D-1")
        self.assertEqual(t.count("add_document"), 1)

    def test_add_document_network_ambiguous_single_attempt(self):
        c, t = _client({"add_document": ConnectionError("lost")})
        with self.assertRaises(ProviderError) as e:
            c.add_document({}, "tok")
        self.assertEqual(e.exception.code, "scts_create_outcome_unknown")
        self.assertTrue(e.exception.ambiguous)
        self.assertFalse(e.exception.retryable)
        self.assertEqual(t.count("add_document"), 1)

    def test_add_document_5xx_ambiguous_single_attempt(self):
        c, t = _client({"add_document": sx.FakeResponse(503, {})})
        with self.assertRaises(ProviderError) as e:
            c.add_document({}, "tok")
        self.assertTrue(e.exception.ambiguous)
        self.assertEqual(t.count("add_document"), 1)

    def test_add_document_4xx_hard_rejection(self):
        c, t = _client({"add_document": sx.FakeResponse(400, {})})
        with self.assertRaises(ProviderError) as e:
            c.add_document({}, "tok")
        self.assertFalse(e.exception.ambiguous)
        self.assertFalse(e.exception.retryable)
        self.assertTrue(e.exception.code.startswith("scts_create_rejected"))
        self.assertEqual(t.count("add_document"), 1)

    # -- adapter: base64 payload + normalization --
    def test_create_document_payload_and_mapping(self):
        ad, t = _adapter({"add_document": sx.add_document_ok("DOC9", 2)})
        ctx = {"doc_code": "PR-1", "title": "T", "amount": 100, "files": [
            {"order": 0, "name": "a.pdf", "content": b"%PDF-hello", "can_be_signed": 1,
             "is_supporting_document": 0, "share_with_partner": 0},
            {"order": 1, "name": "b.pdf", "content": b"%PDF-world", "can_be_signed": 0,
             "is_supporting_document": 1, "share_with_partner": 1}]}
        res = ad.create_document(ctx)
        self.assertEqual(res["document_id"], "DOC9")
        self.assertEqual(res["files"], [{"order": 0, "file_id": "F0"},
                                        {"order": 1, "file_id": "F1"}])
        body = t.last_body("add_document")
        self.assertEqual(body["files"][0]["originalBase64"],
                         base64.b64encode(b"%PDF-hello").decode())
        self.assertNotIn("content", body["files"][0])  # raw bytes never in the payload dict
        self.assertIs(body["files"][0]["canBeSigned"], True)
        self.assertIs(body["files"][1]["isSupportingDocument"], True)
        self.assertIs(body["files"][1]["sharedWithPartner"], True)
        self.assertEqual((body["docCode"], body["title"], body["docAmount"]), ("PR-1", "T", 100))

    def test_create_document_ambiguous_propagates(self):
        ad, t = _adapter({"add_document": ConnectionError("lost")})
        with self.assertRaises(ProviderError) as e:
            ad.create_document({"files": []})
        self.assertTrue(e.exception.ambiguous)
        self.assertEqual(e.exception.code, "scts_create_outcome_unknown")

    def test_create_document_no_document_id_errors(self):
        ad, t = _adapter({"add_document": sx.FakeResponse(200, {"documentFiles": []})})
        with self.assertRaises(ProviderError) as e:
            ad.create_document({"files": []})
        self.assertEqual(e.exception.code, "scts_create_no_document_id")

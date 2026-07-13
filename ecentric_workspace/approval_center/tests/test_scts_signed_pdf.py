# Copyright (c) 2026, eCentric and contributors
"""SCTS signed-PDF retrieval (S2B-C1): client get_pdf fail-closed response handling +
adapter get_signed_document validation. Pure, mocked transport - no network, no bytes
in logs.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_scts_signed_pdf
"""
import base64
import hashlib

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign.providers.base import ProviderError
from ecentric_workspace.approval_center.esign.providers.scts_client import SctsClient
from ecentric_workspace.approval_center.tests import scts_fixtures as sx

PDF = b"%PDF-1.4 signed\n%%EOF"


def _client(script, retry_limit=2):
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


class TestSctsSignedPdf(FrappeTestCase):
    def test_binary_pdf_response(self):
        c, t = _client({"get_pdf": sx.pdf_binary_response(PDF)})
        self.assertEqual(c.get_pdf("D", "F", "tok"), PDF)

    def test_base64_json_response(self):
        c, t = _client({"get_pdf": sx.pdf_base64_response(PDF, field="fileBase64")})
        self.assertEqual(c.get_pdf("D", "F", "tok"), PDF)

    def test_unrecognized_json_is_fail_closed(self):
        c, t = _client({"get_pdf": sx.FakeResponse(200, {"weird": "x"})})
        with self.assertRaises(ProviderError) as e:
            c.get_pdf("D", "F", "tok")
        self.assertEqual(e.exception.code, "scts_signed_pdf_contract_unresolved")
        self.assertFalse(e.exception.retryable)

    def test_empty_binary_rejected(self):
        c, t = _client({"get_pdf": sx.FakeResponse(200, content=b"",
                                                   headers={"Content-Type": "application/pdf"})})
        with self.assertRaises(ProviderError) as e:
            c.get_pdf("D", "F", "tok")
        self.assertEqual(e.exception.code, "scts_signed_pdf_empty")

    def test_5xx_retries_then_succeeds(self):
        c, t = _client({"get_pdf": [sx.FakeResponse(503), sx.pdf_binary_response(PDF)]},
                       retry_limit=2)
        self.assertEqual(c.get_pdf("D", "F", "tok"), PDF)
        self.assertEqual(t.count("get_pdf"), 2)

    def test_4xx_not_retried(self):
        c, t = _client({"get_pdf": sx.FakeResponse(404)}, retry_limit=3)
        with self.assertRaises(ProviderError) as e:
            c.get_pdf("D", "F", "tok")
        self.assertFalse(e.exception.retryable)
        self.assertEqual(t.count("get_pdf"), 1)

    def test_adapter_returns_content_sha_size(self):
        ad, t = _adapter({"get_pdf": sx.pdf_binary_response(PDF)})
        r = ad.get_signed_document("D", "F")
        self.assertEqual(r["content"], PDF)
        self.assertEqual(r["sha256"], hashlib.sha256(PDF).hexdigest())
        self.assertEqual(r["size"], len(PDF))

    def test_adapter_rejects_non_pdf(self):
        ad, t = _adapter({"get_pdf": sx.FakeResponse(200, content=b"NOTPDF",
                                                     headers={"Content-Type": "application/pdf"})})
        with self.assertRaises(ProviderError) as e:
            ad.get_signed_document("D", "F")
        self.assertEqual(e.exception.code, "scts_signed_pdf_not_pdf")

    def test_base64_variant_field_names(self):
        for field in ("pdfBase64", "fileContent", "signedFileBase64"):
            c, t = _client({"get_pdf": sx.pdf_base64_response(PDF, field=field)})
            self.assertEqual(c.get_pdf("D", "F", "tok"), PDF)

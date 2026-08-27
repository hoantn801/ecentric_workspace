# Copyright (c) 2026, eCentric and contributors
"""The signature-listing endpoint must stay System-Manager-only and must never leak
signature images or certificate material.

Onboarding a signer needs `signature_id`, and `verify_mapping` rightly refuses any id the
user does not own. Before this endpoint existed the only way to obtain a valid id was to
read it out of a captured browser request, so onboarding depended on luck. Opening that up
is worth doing, but it is exactly the kind of endpoint that quietly grows: a "just add the
image so the UI can preview it" change would turn a lookup into a signature-material leak.
These checks read the source so such a change cannot land unnoticed.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _api_source():
    """Di NGUOC len tim goc app thay vi dem so cap thu muc: dot reorg thang 8 da giet 29 bo
    test chi vi chung dem cung so cap. Khong thay thi NEM loi kem duong da di qua."""
    tried = []
    root = _HERE
    for _i in range(8):
        path = os.path.join(root, "platform", "esign", "api.py")
        tried.append(path)
        if os.path.exists(path):
            return io.open(path, encoding="utf-8").read()
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay platform/esign/api.py. Da thu:\n  " + "\n  ".join(tried))


def _body(src, func):
    m = re.search(r"\ndef %s\(.*?\n(.*?)(?=\n@frappe\.whitelist|\Z)" % func, src, re.S)
    assert m, "khong tim thay ham %s" % func
    return m.group(1)


class TestListSctsSignatures(unittest.TestCase):
    def setUp(self):
        self.src = _api_source()

    def test_endpoint_exists_and_is_whitelisted(self):
        self.assertIn("def list_scts_signatures(", self.src)
        self.assertRegex(self.src, r"@frappe\.whitelist\(\)\s*\ndef list_scts_signatures\(")

    def test_requires_system_manager(self):
        self.assertIn("perms.assert_system_manager()", _body(self.src, "list_scts_signatures"))

    def test_returns_only_safe_identifier_fields(self):
        body = _body(self.src, "list_scts_signatures")
        returned = set(re.findall(r'"(\w+)":\s*r\.get\(', body))
        self.assertEqual(returned, {"id", "signerId", "type", "company"},
                         "chi duoc tra ve dinh danh + nhan an toan, khong them truong nao khac")

    def test_never_returns_signature_material(self):
        # Bo docstring truoc khi soi: cau "no images, no certificate" nam trong loi giai thich
        # chinh la thu ta muon giu, khong phai vi pham.
        body = re.sub(r'"""[\s\S]*?"""', "", _body(self.src, "list_scts_signatures")).lower()
        for banned in ("image", "base64", "certificate", "cert_", "hsm", "private", "pfx", "p12"):
            self.assertNotIn(banned, body,
                             "endpoint nay khong duoc cham vao vat lieu chu ky: %s" % banned)

    def test_does_not_write_anything(self):
        body = _body(self.src, "list_scts_signatures")
        for banned in ("db_set", "db.set_value", ".save(", ".insert(", "frappe.delete_doc"):
            self.assertNotIn(banned, body, "endpoint phai la CHI DOC: %s" % banned)

    def test_fails_closed_without_enabled_settings(self):
        body = _body(self.src, "list_scts_signatures")
        self.assertIn("integration_enabled", body)
        self.assertIn("frappe.throw", body)


class TestVerifyMappingStillStrict(unittest.TestCase):
    """Seeding hang loat chi an toan khi verify_mapping van tu choi chu ky khong thuoc user."""

    def test_ownership_is_checked_against_both_ids(self):
        body = _body(_api_source(), "verify_mapping")
        self.assertIn('str(x.get("id")) == str(m.signature_id)', body)
        self.assertIn('str(x.get("signerId")) == str(m.scts_user_id)', body)

    def test_refuses_when_not_owned(self):
        body = _body(_api_source(), "verify_mapping")
        self.assertIn("if not owned:", body)
        self.assertIn("frappe.throw", body.split("if not owned:")[1][:200])


if __name__ == "__main__":
    unittest.main()

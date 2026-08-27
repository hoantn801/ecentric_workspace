# Copyright (c) 2026, eCentric and contributors
"""A signing slot nobody has filled yet must still say WHICH slot it is.

Night of 2026-08-27. `EC-DSR-2026-00012` would not sign and the diagnosis burned hours on
six hypotheses that the data refuted one after another. The whole time the read-out looked
like this:

    hoan.tran@ecentric.vn   signed   04:12
    (chua gan)              pending  -
    (chua gan)              pending  -
    lien.vu@ecentric.vn     signed   17:59
    hoan.tran@ecentric.vn   signed   11:54

Two anonymous rows. Which approval level are they? Which one is waiting on Phuong? No way
to tell - so every question about them had to be answered by guessing.

eContract had been sending `role`, `roleText` and the sign type on every one of those rows
the entire time. Our normalizer dropped them and kept only email and status. The provider
was not silent; we were not listening.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
    tried = []
    root = _HERE
    for _i in range(8):
        path = os.path.join(root, *parts)
        tried.append(path)
        if os.path.exists(path):
            return io.open(path, encoding="utf-8").read()
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay %s. Da thu:\n  %s" % (parts[-1], "\n  ".join(tried)))


class TestNormalizerKeepsTheRole(unittest.TestCase):
    def setUp(self):
        src = _src("platform", "esign", "providers", "scts.py")
        m = re.search(r"def _norm_signer\(s\):(.*?)(?=\n    @staticmethod)", src, re.S)
        assert m, "khong tim thay _norm_signer"
        self.body = m.group(1)

    def test_role_survives_normalisation(self):
        self.assertIn('"role": s.get("role")', self.body)

    def test_role_text_survives(self):
        self.assertIn('"role_text": s.get("roleText")', self.body)

    def test_sign_type_survives(self):
        self.assertIn('"sign_type"', self.body,
                      "loai o ky (Ky chinh / Tham gia) quyet dinh ai ky duoc vao do")

    def test_identity_fields_are_still_there(self):
        for f in ('"user_id"', '"email"', '"status"', '"signed_at"'):
            self.assertIn(f, self.body, "khong duoc lam mat truong cu khi them truong moi")

    def test_no_personal_identity_documents_are_pulled_through(self):
        for banned in ("cccd", "dob", "identityPlace", "identityDate", "mobile"):
            self.assertNotIn(banned, self.body,
                             "eContract co tra truong nay nhung ta KHONG duoc lay: %s" % banned)


class TestDiagnosticExposesIt(unittest.TestCase):
    def setUp(self):
        src = _src("platform", "esign", "api.py")
        m = re.search(r'"signers": \[\{(.*?)\}\s*\n?\s*for ', src, re.S)
        assert m, "khong tim thay khoi signers cua esign_document_state"
        self.block = m.group(1)

    def test_the_endpoint_returns_the_role(self):
        self.assertIn('"role"', self.block)
        self.assertIn('"role_text"', self.block)
        self.assertIn('"sign_type"', self.block)

    def test_it_still_returns_who_and_when(self):
        for f in ('"email"', '"status"', '"signed_at"'):
            self.assertIn(f, self.block)


if __name__ == "__main__":
    unittest.main()

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


def _code_only(body):
    """Bo docstring va chu thich. Mot phep kiem soi ca loi giai thich se bat oan chinh cau
    van dang noi ro vi sao KHONG dung thu do."""
    body = re.sub(r'"""[\s\S]*?"""', "", body)
    return re.sub(r"(?m)^\s*#.*$", "", body)


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
        """Danh sach truong duoc phep - moi lan them phai ghi ly do NGAY TAI DAY.

        03/09 them `has_hsm` (bool) va `sign_token` (so). Ly do: anh Lam co HAI chu ky
        `ky-chinh`, mapping tro vao mot; chu ky `signToken=1` ky bang token tai may qua
        OfficeSignTool nen ERP khong ky thay duoc, `0` + co HSM thi ky duoc tu may chu. Khong
        co hai co nay thi khong tra loi noi "cai nao dung duoc" ma khong dang nhap cong bang
        tai khoan nguoi khac. Hai co la CO/KHONG va MOT SO - khong phai id chung thu, khong
        phai vat lieu.
        """
        body = _body(self.src, "list_scts_signatures")
        # Regex nay bat `"k": r.get(` - truong boc trong bool() (`active`, `has_hsm`) khong
        # khop, va do la co y: bool() la lop bao dam khong lo gia tri tho. `has_hsm` co phep
        # kiem rieng ben duoi.
        returned = set(re.findall(r'"(\w+)":\s*r\.get\(', body))
        self.assertEqual(returned, {"id", "signerId", "type", "company", "sign_token"},
                         "chi duoc tra ve dinh danh + nhan an toan + sign_token, khong them "
                         "truong nao khac")
        boc_bool = set(re.findall(r'"(\w+)":\s*bool\(r\.get\(', body))
        self.assertEqual(boc_bool, {"active", "has_hsm"},
                         "truong bool chi co active va has_hsm")

    def test_never_returns_signature_material(self):
        # Bo docstring VA chu thich truoc khi soi: cau "no images, no certificate" nam trong
        # loi giai thich chinh la thu ta muon giu, khong phai vi pham.
        #
        # `hsm` -> `hsmid`/`hsmcertid`/`hsm_id`: cam ID cua chung thu HSM, khong cam chu
        # `has_hsm` (bool). Ban dau cam ca chuoi `hsm`, dung, cho toi khi can mot co co/khong.
        body = _code_only(_body(self.src, "list_scts_signatures")).lower()
        for banned in ("image", "base64", "certificate", "cert_", "hsmid", "hsmcertid",
                       "hsm_id", "private", "pfx", "p12"):
            self.assertNotIn(banned, body,
                             "endpoint nay khong duoc cham vao vat lieu chu ky: %s" % banned)

    def test_has_hsm_la_bool_khong_phai_id(self):
        """Neu ai do doi `bool(r.get("has_hsm"))` thanh `r.get("hsmCertId")` thi test tren
        van xanh (khong co chuoi cam trong api.py - id nam o adapter). Chan ngay tai day."""
        body = _code_only(_body(self.src, "list_scts_signatures"))
        self.assertIn('"has_hsm": bool(r.get("has_hsm"))', body,
                      "has_hsm phai di qua bool() - tra thang gia tri la tra id chung thu")

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


class TestSignatureOverlayStaysNarrow(unittest.TestCase):
    """Endpoint tra ve ANH chu ky - pham vi phai chat, va phai chat MAI."""

    def setUp(self):
        self.body = _body(_api_source(), "document_signature_overlay")

    def test_only_for_people_who_actually_signed_this_document(self):
        self.assertIn('== "signed"', self.body,
                      "chi lay dong nha cung cap bao DA KY")
        self.assertIn("signed_emails", self.body)

    def test_attribution_comes_from_our_own_completed_legs(self):
        """Gan chu ky theo CHAN KY, khong theo email trong danh sach ung vien.

        28/08: ban khop email da ve chu ky vao o "Direct Manager Review" chi vi cung mot
        nguoi da ky voi vai NGUOI TRINH va tinh co la ung vien cua cap do. Nha cung cap co
        MOT chu ky; man hinh hien HAI.
        """
        self.assertIn('"status": "Approval Completed"', self.body)
        # 28/08: tra THANG request_level ra day thi khong o ky nao khop, vi o ky dinh danh
        # cap bang EC Approval LEVEL con chan ky luu EC Approval REQUEST Level. Phai doi.
        # Phep kiem giu nguyen y dinh goc (gan theo CHAN KY, khong theo email), chi doi
        # cho cai duoc gan.
        self.assertIn('_source_level_of(leg.get("request_level"))', self.body)
        self.assertIn('"kind"', self.body)
        self.assertNotIn("candidates", self.body,
                         "khong duoc suy tu danh sach ung vien cua o ky")

    def test_requires_business_view_permission(self):
        self.assertIn('_business_args("EC Payment Request"', self.body,
                      "phai gioi han o nguoi da duoc xem chinh yeu cau nay")

    def test_uses_the_accessor_that_actually_returns_an_image(self):
        # list_user_signatures() chuan hoa qua _norm_signature va LAM RUNG base64Image ->
        # dung no o day se luon tra None ma khong bao gi.
        # Soi CODE, khong soi chu thich: chinh cai bay nay da lam mot phep kiem truoc do do oan.
        self.assertIn("adapter.signature_image(", self.body)
        self.assertNotIn("list_user_signatures", _code_only(self.body))

    def test_image_lookup_goes_through_a_verified_mapping(self):
        self.assertIn("perms.verified_mapping(", self.body,
                      "khong duoc tra anh cho danh tinh chua xac minh")

    def test_a_missing_image_never_hides_the_fact_of_signing(self):
        self.assertIn("except Exception:", self.body)
        idx = self.body.index("except Exception:")
        self.assertIn("out.append(", self.body[idx:],
                      "loi lay anh khong duoc lam mat dong 'nguoi nay da ky'")

    def test_does_not_write_anything(self):
        for banned in ("db_set", "db.set_value", ".save(", ".insert(", "frappe.delete_doc"):
            self.assertNotIn(banned, self.body, "phai la CHI DOC: %s" % banned)

    def test_never_returns_certificate_material(self):
        low = _code_only(self.body).lower()
        for banned in ("hsmcert", "certificate", "private", "pfx", "p12"):
            self.assertNotIn(banned, low, "khong duoc cham vao vat lieu chung thu: %s" % banned)


if __name__ == "__main__":
    unittest.main()

# Copyright (c) 2026, eCentric and contributors
"""Three control holes found by a QC sweep on the night of 2026-08-28. Two of them I wrote
that same night, which is the part worth remembering.

1. `document_signature_overlay` returned signature IMAGES after calling only
   `_business_args()`. That helper checks the record exists - it is not a permission check.
   Every other read endpoint in the file calls `perms.assert_can_view_business`; the one I
   added did not. Any logged-in employee who could guess a request name could read who signed,
   when, and what their signature looks like.

   The test I had written for it asserted the string `_business_args("EC Payment Request"`
   was present - so it certified the hole instead of finding it. A test that checks for the
   presence of a call says nothing about whether that call does what you assumed.

2. `assert_level_completable` called `level_requires_signature` WITHOUT `final_level`. Under
   the "Final Approval Level Only" policy that branch reads
   `final_level is not None and ...`, so it was always False and the gate returned early.
   That gate is the only thing engine.approve() and admin_override_current_level() rely on:
   plain "Duyệt" could complete the final level with no signature at all, while the UI still
   said a signature was required - because service.py and inbox.py do pass final_level.

3. `lifecycle.on_request_reopened` reset `requester_signature_status` on the BUSINESS
   document. That field lives on EC Approval Request. The write was wrapped in
   `except Exception`, so it failed into a log line while the caller carried on believing the
   reset had happened - and the requester was then told they had already signed, with no way
   to sign the new package. Writing to the wrong place and swallowing the error is worse than
   not trying, because it looks like it worked.
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


def _fn(src, name):
    m = re.search(r"\ndef %s\(.*?\n(.*?)(?=\n@frappe\.whitelist|\ndef |\Z)" % name, src, re.S)
    assert m, "khong tim thay ham %s" % name
    return m.group(1)


class TestEveryReadEndpointChecksPermission(unittest.TestCase):
    """Quet TOAN BO file, khong chi ham vua sua - de lan sau them endpoint moi cung bi bat."""

    #: These take no business document, so business-view permission does not apply. They
    #: carry their OWN gate (assert_system_manager) - asserted separately below.
    _SM_ONLY = {"test_connection", "verify_mapping", "list_scts_signatures",
                "provider_document_shape", "esign_document_state", "signing_inbox"}

    def setUp(self):
        self.src = _src("platform", "esign", "api.py")

    def test_business_args_is_not_a_permission_check(self):
        body = _fn(self.src, "_business_args")
        self.assertNotIn("perms.", body,
                         "neu ham nay tro thanh phep kiem quyen thi phai sua lai ca test nay")
        self.assertIn("frappe.db.exists", body)

    #: module alias -> file, for following one level of delegation
    _MODULES = {"svc": "service.py", "requester": "requester.py", "pkgsvc": "package.py",
                "ps": "placement_service.py", "ds": "document_setup.py",
                "sp": "signer_plan.py", "pilot": "pilot.py", "sf": "signed_files.py",
                "ui_state": "ui_state.py", "multi_sign": "multi_sign.py"}

    def _delegate_checks(self, body):
        """Mot endpoint co the KHONG tu kiem quyen ma uy quyen cho service. Di theo mot cap
        uy quyen va xem ham dich co cong nao khong. Ban dau tien cua phep kiem nay khong di
        theo uy quyen nen to oan 15 endpoint - to oan nhieu thi nguoi ta ngung doc ket qua."""
        for alias, fname in self._MODULES.items():
            for call in re.findall(r"\b%s\.(\w+)\(" % alias, body):
                try:
                    target = _src("platform", "esign", fname)
                except AssertionError:
                    continue
                m = re.search(r"\ndef %s\(.*?\n(.*?)(?=\ndef |\Z)" % call, target, re.S)
                if not m:
                    continue
                target_body = m.group(1)
                # Hai dang cong hop le, deu duoc chap nhan:
                #  - goi mot ham assert (luu y KHONG dung \b: nhieu cong ten la
                #    _assert_can_classify, va \b khong khop khi truoc no la dau gach duoi)
                #  - kiem noi tuyen roi nem PermissionError (requester.py lam kieu nay)
                if re.search(r"_?assert_\w+\(", target_body):
                    return True
                if "frappe.PermissionError" in target_body:
                    return True
        return False

    def test_endpoints_taking_a_payment_request_check_view_permission(self):
        offenders = []
        for m in re.finditer(r"\ndef (\w+)\(payment_request_name[^)]*\):(.*?)(?=\n@frappe|\ndef |\Z)",
                             self.src, re.S):
            name, body = m.group(1), m.group(2)
            if name.startswith("_") or name in self._SM_ONLY:
                continue
            if re.search(r"perms\._?assert_\w+\(", body):
                continue
            if self._delegate_checks(body):
                continue
            offenders.append(name)
        self.assertEqual(offenders, [],
                         "endpoint nhan payment_request_name ma KHONG kiem quyen va cung "
                         "khong uy quyen cho ham co kiem quyen: %s" % offenders)

    def test_the_signature_image_endpoint_specifically(self):
        body = _fn(self.src, "document_signature_overlay")
        self.assertIn('perms.assert_can_view_business("EC Payment Request"', body)

    def test_system_manager_endpoints_really_are_gated(self):
        for name in ("list_scts_signatures", "provider_document_shape", "esign_document_state"):
            self.assertIn("perms.assert_system_manager()", _fn(self.src, name),
                          "%s nam trong danh sach mien nhung khong co cong SM" % name)


class TestSignatureGateActuallyRuns(unittest.TestCase):
    def setUp(self):
        self.src = _src("platform", "esign", "guard.py")

    def test_assert_level_completable_passes_final_level(self):
        body = _fn(self.src, "assert_level_completable")
        self.assertIn("final_level=request_final_level(req.name)", body,
                      "thieu final_level -> chinh sach 'Final Approval Level Only' tat han cong")

    def test_every_caller_passes_final_level(self):
        """Quet moi noi goi, khong chi cho vua sua."""
        offenders = []
        for path in (("platform", "esign", "guard.py"),
                     ("platform", "esign", "service.py"),
                     ("platform", "esign", "inbox.py")):
            src = _src(*path)
            for m in re.finditer(r"level_requires_signature\(([^)]*)\)", src, re.S):
                args = m.group(1)
                if "def " in args:
                    continue
                if "final_level" not in args:
                    offenders.append("%s: %s" % (path[-1], " ".join(args.split())[:70]))
        self.assertEqual(offenders, [], "goi thieu final_level: %s" % offenders)

    def test_the_policy_branch_is_the_one_that_depends_on_it(self):
        body = _fn(self.src, "level_requires_signature")
        self.assertIn("final_level is not None", body,
                      "neu nhanh nay doi thi phep kiem tren khong con y nghia")


class TestRequesterResetTargetsTheRightDoctype(unittest.TestCase):
    """Bai hoc 28/08 - giu lai du hanh vi da doi.

    Ban dau `on_request_reopened` reset `requester_signature_status` khi tao goi phien ban
    moi, va no ghi NHAM vao pkg.business_doctype ("EC Payment Request") - mot DocType khong
    co cot do. Lenh ghi lai duoc boc trong `except Exception`, nen no that bai thanh mot dong
    log trong khi luong tin la da reset xong. Nguoi de nghi bi bao "da ky cho yeu cau nay" va
    goi moi khong bao gio ky duoc. Ghi sai cho + nuot loi con te hon khong lam gi: no TRONG
    NHU da chay.

    Tu 31/08 khong con tao goi phien ban moi (xem test_reopen_revises_package), nen khong con
    lenh reset nao ca. Phep kiem con lai la phep quan trong nhat va van dung nguyen: ham nay
    khong duoc nuot loi, va khong duoc ghi vao chung tu nghiep vu.
    """

    def setUp(self):
        self.src = _src("platform", "esign", "lifecycle.py")
        self.body = _fn(self.src, "on_request_reopened")

    def test_khong_con_reset_vi_khong_con_tao_goi_moi(self):
        code = re.sub(r'"""[\s\S]*?"""', "", self.body)
        code = re.sub(r"(?m)^\s*#.*$", "", code)
        self.assertNotIn("requester_signature_status", code,
                         "khong con goi phien ban moi thi khong co gi de reset")

    def test_it_never_writes_to_the_business_doctype(self):
        self.assertNotIn("pkg.business_doctype, pkg.business_name,", self.body,
                         "truong nay khong ton tai tren chung tu nghiep vu")

    def test_ham_nay_khong_ghi_gi_ca(self):
        # Gio no chi doc roi quyet dinh cho qua hay dung han.
        code = re.sub(r'"""[\s\S]*?"""', "", self.body)
        code = re.sub(r"(?m)^\s*#.*$", "", code)
        for write in ("set_value", "insert(", "events.emit"):
            self.assertNotIn(write, code,
                             "tu choi thi khong duoc de lai dau vet ghi nao")

    def test_the_failure_is_not_swallowed(self):
        # Soi CODE, khong soi chu thich: chu thich o day GIAI THICH vi sao khong duoc nuot
        # loi, va mot phep kiem ngay tho se bat oan chinh cau van do. Da vap dung bay nay
        # hai lan trong dem.
        code = re.sub(r'"""[\s\S]*?"""', "", self.body)
        code = re.sub(r"(?m)^\s*#.*$", "", code)
        self.assertNotIn("except Exception", code,
                         "nuot loi o day = tin la da reset trong khi chua, va khoa nguoi trinh")

    def test_the_field_lives_where_we_think(self):
        schema = _src("approval_center", "doctype", "ec_approval_request",
                      "ec_approval_request.json")
        self.assertIn('"requester_signature_status"', schema)


if __name__ == "__main__":
    unittest.main()

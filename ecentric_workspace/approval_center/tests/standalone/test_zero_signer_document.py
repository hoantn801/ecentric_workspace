# Copyright (c) 2026, eCentric and contributors
"""A document with no signers cannot be "fully signed", whatever the provider calls it.

The check walked the signer list looking for anyone not yet signed, then fell through to
"the provider says the status is terminal, so we are done". On an EMPTY list the walk finds
nothing to object to - so zero signers read exactly like everyone-has-signed.

This is not hypothetical. On 2026-08-28 a document created from the ERP appeared on the
provider's portal with all five signature areas present and nobody assigned to any of them
("Tham gia: --- / Chua co"). That is the UAT VOID 5 class of failure: the approver is told
the document is signed while the PDF carries no signature at all.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
    root = _HERE
    tried = []
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


class _Doc(object):
    def __init__(self, status, signers):
        self.status = status
        self.signers = signers


def _load_checker():
    """Chay THAT doan quyet dinh, khong grep - `if not signers` co the bi vo hieu ma
    chuoi van con trong source."""
    # Chay TRON ven doan quyet dinh - tu poll_status toi het ham. Ban dau cat toi moc
    # `exp_ids`, nhung 01/09 khoi doi chieu danh tinh duoc dua LEN truoc terminal-status
    # (va lo hong UAT VOID 5 nga khac), nen cat theo moc do la bo mat chinh phan vua sua.
    src = _src("platform", "esign", "signed_files.py")
    m = re.search(r"(?m)^    doc = adapter\.poll_status.*?\n    return True, \"all_expected_signers_signed\"",
                  src, re.S)
    assert m, "khong tim thay doan quyet dinh trong _terminal_signed_ok"
    body = m.group(0)
    fn = "def decide(adapter, pkg):\n" + body + "\n    return None, 'fell_through'\n"
    g = {"_TERMINAL_SIGNED": ("signed", "completed", "complete", "done", "finished", "success"),
         # Nguoi ky ky vong: test khai qua pkg.expected_pairs = [(id, email), ...].
         # Nguon doi tu `_expected_signers` (hai tap hop) sang `_expected_signer_pairs`
         # (giu ghep doi) ngay 01/09 - ban gia phai theo, khong thi no goi ham that va no.
         "_expected_signer_pairs":
             lambda name: list(getattr(_CUR_PKG[0], "expected_pairs", []))}
    exec(compile(fn, "decide", "exec"), g)
    return g["decide"]


_CUR_PKG = [None]


class _Adapter(object):
    def __init__(self, doc):
        self._doc = doc

    def poll_status(self, doc_id):
        return self._doc


class _Pkg(object):
    scts_document_id = "DOC-1"
    name = "PKG-1"
    #: [(provider_user_id, email)] nguoi ky KY VONG. Tu 01/09 danh tinh duoc xet KE CA
    #: khi tai lieu terminal, nen moi ca "ky that" phai khai ai la nguoi duoc ky.
    expected_pairs = [("u1", None)]


class TestZeroSignersIsNeverProof(unittest.TestCase):
    def setUp(self):
        self.decide = _load_checker()
        _CUR_PKG[0] = _Pkg()

    def test_completed_with_no_signers_is_refused(self):
        ok, why = self.decide(_Adapter(_Doc("Hoàn thành", [])), _Pkg())
        self.assertFalse(ok, "0 nguoi ky ma van bao da ky xong")
        self.assertEqual(why, "no_signers_on_document")

    def test_it_refuses_before_reading_the_terminal_status(self):
        """Ke ca khi provider dung dung chu trong _TERMINAL_SIGNED."""
        for status in ("signed", "completed", "done", "success"):
            ok, why = self.decide(_Adapter(_Doc(status, [])), _Pkg())
            self.assertFalse(ok, "status=%r + 0 nguoi ky -> van bao da ky" % status)

    def test_a_real_signed_signer_still_passes(self):
        pkg = _Pkg()
        _CUR_PKG[0] = pkg
        ok, why = self.decide(
            _Adapter(_Doc("completed", [{"status": "signed", "user_id": "u1"}])), pkg)
        self.assertTrue(ok, "chan qua tay: chung tu ky that bi tu choi")
        self.assertEqual(why, "terminal_and_all_expected_signers_signed")

    def test_terminal_KHONG_con_bo_qua_doi_chieu_danh_tinh(self):
        """01/09: `status=completed` tung lam khoi doi chieu danh tinh thanh ma chet.

        Nguoi NGOAI ky thay, hoac thieu nguoi ky ky vong, ma provider dan nhan "completed"
        thi truoc day van qua cong. Terminal la dieu kien CAN, khong phai DU.
        """
        pkg = _Pkg()
        _CUR_PKG[0] = pkg
        ok, why = self.decide(
            _Adapter(_Doc("completed", [{"status": "signed", "user_id": "NGUOI-LA"}])), pkg)
        self.assertFalse(ok, "nguoi ky la van qua cong khi tai lieu terminal")
        # Hai ly do deu dung: nguoi ky vong VANG MAT, va nguoi co mat la NGUOI LA. Phep
        # kiem nay quan tam "co bi chan khong", khong ap dat thu tu phat hien.
        self.assertTrue(
            any(k in str(why) for k in ("expected_signer_absent", "unexpected_signer_identity")),
            "phai chan vi danh tinh, ly do nhan duoc: %r" % (why,))

    def test_a_pending_signer_still_blocks(self):
        ok, why = self.decide(
            _Adapter(_Doc("completed", [{"status": "signed"}, {"status": "pending"}])), _Pkg())
        self.assertFalse(ok)
        self.assertIn("non_signed_signer_present", why)


if __name__ == "__main__":
    unittest.main()

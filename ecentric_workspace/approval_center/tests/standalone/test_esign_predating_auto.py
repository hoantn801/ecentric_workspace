# Copyright (c) 2026, eCentric and contributors
"""Chu ky KY TRUC TIEP TREN CONG truoc khi ERP gui lenh - tu cho qua khi ky SAU luc cap MO
(27/11/2026, EC-PAYR-2026-00604 / 00726: anh Lam ky tren cong 23/11 18:03, cap 4 da mo tu
truoc, 25/11 moi bam "Duyet & Ky" -> Manual Review, phai doi soat tay).

Chot:
  1. Co `predating_floor` (luc cap mo - dung sai): ky sau san -> verified_predating_auto.
  2. Ky TRUOC san (cap chua mo) -> van tu choi `signature_predates_request`.
  3. Khong co san -> y het truoc (doi soat tay van la `verified_predating_manual`).
  4. Moi phep kiem khac giu nguyen (sai mau chu ky van tu choi).
  5. service._predating_floor: chan nguoi de nghi / khong dem duoc / cap chua mo -> None.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


def _base():
    """Nap providers/base.py voi frappe gia (module co `import frappe` o dau)."""
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.utils = types.ModuleType("frappe.utils")
    saved = {k: sys.modules.get(k) for k in ("frappe", "frappe.utils")}
    sys.modules["frappe"] = fk
    sys.modules["frappe.utils"] = fk.utils
    try:
        mod = types.ModuleType("base_under_test")
        exec(compile(_read("platform", "esign", "providers", "base.py"), "base.py", "exec"),
             mod.__dict__)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


_B = _base()
_DOC = "74769fab"
_WHO = "vinh.vu@ecentric.vn"


def _state(signers):
    return _B.NormalizedDocState(document_id=_DOC, status="processing",
                                 files=[], signers=signers, raw={})


def _signer(email=_WHO, status="signed", signed_at="08/09/2026 23:48"):
    return {"email": email, "status": status, "signed_at": signed_at,
            "user_id": None, "signature_id": None, "role": "thamgia"}


def _expected(**kw):
    from datetime import datetime
    base = {"document_id": _DOC, "user_id": None, "email": _WHO,
            # ERP hoi luc 11:17 sang hom sau (11:19 tru dung sai 120 giay)
            "signed_after": datetime(2026, 9, 9, 11, 17, 0),
            "prior_signatures": 0}
    base.update(kw)
    return base




def _verify(signers, **kw):
    return _B.SignatureProviderAdapter.verify_signed_result(_state(signers), _expected(**kw))


class TestTuDongChoQuaKhiKySauLucCapMo(unittest.TestCase):
    def test_ky_sau_luc_cap_mo_thi_cho_qua_va_noi_ro(self):
        from datetime import datetime
        res = _verify([_signer()], allow_predating=True,
                      predating_floor=datetime(2026, 9, 8, 20, 0, 0))
        self.assertTrue(res.ok)
        self.assertTrue(res.reason.startswith("verified_predating_auto:"), res.reason)

    def test_ky_TRUOC_luc_cap_mo_van_tu_choi(self):
        from datetime import datetime
        res = _verify([_signer()], allow_predating=True,
                      predating_floor=datetime(2026, 9, 9, 8, 0, 0))
        self.assertFalse(res.ok)
        self.assertTrue(res.reason.startswith("signature_predates_request"), res.reason)

    def test_khong_san_van_la_doi_soat_tay(self):
        res = _verify([_signer()], allow_predating=True)
        self.assertTrue(res.reason.startswith("verified_predating_manual:"), res.reason)

    def test_khong_co_co_thi_san_khong_tac_dung(self):
        from datetime import datetime
        res = _verify([_signer()], predating_floor=datetime(2026, 9, 8, 20, 0, 0))
        self.assertFalse(res.ok)

    def test_sai_mau_chu_ky_van_tu_choi(self):
        from datetime import datetime
        s = dict(_signer(), signature_id="khac")
        res = _verify([s], allow_predating=True, signature_id="dung",
                      predating_floor=datetime(2026, 9, 8, 20, 0, 0))
        self.assertFalse(res.ok)


class TestSanTuService(unittest.TestCase):
    def _fn(self):
        src = _read("platform", "esign", "service.py")
        return next(ast.unparse(n) for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.FunctionDef) and n.name == "_predating_floor")

    def test_bo_qua_chan_nguoi_de_nghi_va_khong_dem_duoc(self):
        fn = self._fn()
        self.assertIn("'Requester'", fn)
        self.assertIn("_completed_legs_of_same_signer(dsr) is None", fn)
        self.assertIn("'activated_at'", fn)

    def test_doi_soat_tay_khong_dung_san(self):
        src = _read("platform", "esign", "service.py")
        self.assertIn("floor = None if allow_predating else _predating_floor(dsr)", src)


if __name__ == "__main__":
    unittest.main()

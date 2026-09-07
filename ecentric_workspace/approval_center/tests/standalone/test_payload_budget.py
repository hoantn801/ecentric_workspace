# Copyright (c) 2026, eCentric and contributors
"""AddDocument 413 (07/09, EC-PAYR-2026-00044: 6 PDF = 10,9 MB, gui hai lan base64 = 30,6 MB).

  1. limits: uoc luong = 2 x base64; ngan = 95% x 30.000.000 - envelope; 00044 khong vua,
     bo tep 6,5 MB thi vua.
  2. tasks._fit_payload_budget (code THAT): bo phu luc LON NHAT truoc, ghi su kien
     SupportingFileKeptInErp (ten goc ERP, order, ly do payload_budget); to trinh khong bo;
     chi to trinh ma van vuot -> ProviderError scts_payload_too_large (khong retry).
  3. package.preflight_for_lock: to trinh vuot ngan -> signable_too_large:<MB>; requester co cau.
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")
sys.path.insert(0, _HERE)
from test_provider_document_dead import _tasks            # noqa: E402  (loader code THAT)
from test_provider_files_always_pdf import _package_module, _row  # noqa: E402


def _limits():
    m = types.ModuleType("_limits_under_test")
    with io.open(os.path.join(_ESIGN, "limits.py"), encoding="utf-8") as fh:
        exec(compile(fh.read(), "limits.py", "exec"), m.__dict__)
    return m


SIZES_00044 = [173742, 332274, 494221, 491010, 3243278, 6725632]


class TestLimits(unittest.TestCase):
    def test_uoc_luong_hai_lan_base64(self):
        L = _limits()
        self.assertEqual(L.payload_bytes_for([3]), 8)          # 3 byte -> 4 ky tu x 2
        self.assertEqual(L.payload_bytes_for([4]), 16)         # lam tron len khoi 3
        self.assertLess(L.payload_budget_bytes(), 30_000_000)

    def test_00044_khong_vua_bo_tep_lon_thi_vua(self):
        L = _limits()
        self.assertFalse(L.fits(SIZES_00044))
        self.assertTrue(L.fits(SIZES_00044[:-1]))


def _sent(order, n, signable):
    return {"order": order, "name": "f%d.pdf" % order, "file_dsf": "DSF-%d" % order,
            "can_be_signed": signable, "content": b"x" * n}


class TestFit(unittest.TestCase):
    def _mod(self):
        m = _tasks()
        m._fk.db.get_value = lambda dt, name, field=None, **k: name.replace("DSF-", "goc-") + ".pdf"
        sys.modules["ecentric_workspace.platform.esign.limits"] = _limits()
        return m

    def tearDown(self):
        sys.modules.pop("ecentric_workspace.platform.esign.limits", None)

    def test_bo_phu_luc_lon_nhat_truoc_va_ghi_su_kien(self):
        m = self._mod()
        sent = [_sent(i, n, i < 2) for i, n in enumerate(SIZES_00044)]
        out = m._fit_payload_budget(types.SimpleNamespace(name="PKG-1"), sent)
        self.assertEqual([f["order"] for f in out], [0, 1, 2, 3, 4], "chi bo tep 6,5 MB (order 5)")
        emits = [c for c in m._ev.calls if c[0] == "emit"]
        self.assertEqual(len(emits), 1)
        self.assertEqual(emits[0][1][0], "SupportingFileKeptInErp")
        meta = emits[0][2]["request_meta"]
        self.assertEqual((meta["file"], meta["order"]), ("goc-5.pdf", 5))
        self.assertTrue(meta["reason"].startswith("payload_budget"))

    def test_vua_thi_khong_dong_gi(self):
        m = self._mod()
        out = m._fit_payload_budget(types.SimpleNamespace(name="PKG-1"), [_sent(0, 1000, True), _sent(1, 1000, False)])
        self.assertEqual(len(out), 2); self.assertEqual(m._ev.calls, [])

    def test_chi_to_trinh_ma_van_vuot_thi_tu_choi_ro(self):
        m = self._mod()
        with self.assertRaises(Exception) as cm:
            m._fit_payload_budget(types.SimpleNamespace(name="PKG-1"),
                                  [_sent(0, 8_000_000, True), _sent(1, 8_000_000, True), _sent(2, 100, False)])
        self.assertEqual(cm.exception.code, "scts_payload_too_large")
        self.assertFalse(cm.exception.retryable)


class TestOmitOriginal(unittest.TestCase):
    """Provider Settings.omit_original_base64 (thu nghiem): 1 lan base64 -> ngan gap doi;
    adapter gui OriginalBase64 rong, SCTS 4xx thi gui lai ban day du MOT lan."""

    def test_copies_theo_settings(self):
        L = _limits()
        self.assertEqual(L.payload_copies({}), 2)
        self.assertEqual(L.payload_copies({"omit_original_base64": 1}), 1)
        self.assertEqual(L.payload_copies(types.SimpleNamespace(omit_original_base64=1)), 1)
        self.assertFalse(L.fits(SIZES_00044, 2)); self.assertTrue(L.fits(SIZES_00044, 1))

    def test_adapter_gui_rong_va_gui_lai_khi_4xx(self):
        import ast
        with io.open(os.path.join(_ESIGN, "providers", "scts.py"), encoding="utf-8") as fh:
            src = fh.read()
        fn = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "create_document"][0]
        body = ast.unparse(fn)
        self.assertIn("omit = bool(int(_sval(getattr(self, 'settings', None) or {}, 'omit_original_base64', 0) or 0))", body)
        self.assertIn("'OriginalBase64': '' if omit else b64", body)
        self.assertIn("str(exc.code).startswith('scts_create_rejected_4')", body)
        self.assertIn("d['OriginalBase64'] = d['PdfBase64']", body)
        self.assertEqual(body.count("self._client.add_document(payload, t)"), 2, "dung MOT lan gui lai")
        self.assertIn("getattr(exc, 'ambiguous', False)", body, "mo ho (timeout/5xx) KHONG duoc gui lai")


class TestPreflight(unittest.TestCase):
    def test_to_trinh_vuot_ngan_bi_chan_luc_gui(self):
        big = _row("a.pdf", "application/pdf", 1, 1); big["size_bytes"] = 12_000_000
        errs = _package_module([big])
        self.assertTrue(any(e.startswith("signable_too_large:") for e in errs), errs)

    def test_phu_luc_to_khong_bi_chan_luc_gui(self):
        big = _row("hd.pdf", "application/pdf", 1, 0); big["size_bytes"] = 12_000_000
        errs = _package_module([_row("a.pdf", "application/pdf", 1, 1), big])
        self.assertEqual(errs, [])

    def test_requester_co_cau_tieng_viet(self):
        with io.open(os.path.join(_ESIGN, "requester.py"), encoding="utf-8") as fh:
            self.assertIn('if head == "signable_too_large":', fh.read())


if __name__ == "__main__":
    unittest.main()

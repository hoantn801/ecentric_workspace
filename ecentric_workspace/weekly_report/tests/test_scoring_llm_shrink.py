# Copyright (c) 2026, eCentric and contributors
"""Nhanh NEN trong `_bytes_for_kie` (them 25/09, chat Weekly Report).

Ban goc cua buoc 1: tong PDF vuot tran inline -> bo ca luot Kie, di Google. Dung
ve nguyen tac, nhung Google dang tra 400 tu 17/09 nen "du phong" luc nay la luoi
rach: deck lon se khong bao gio co diem. Hoan chot 25/09 la thu NEN truoc khi bo
cuoc.

Dieu PHAI giu, va la ly do bo test nay ton tai: ky luat tat-ca-hoac-khong-gi
khong duoc suy yeu. Nen duoc thi di Kie voi DU tep; nen khong duoc thi van tra
([], ly_do) nhu cu. Khong bao gio duoc gui mot phan deck -- model van cham diem,
cham tren du lieu thieu, va diem do vao KPI.
"""

import unittest

from ecentric_workspace import gemini_api
from ecentric_workspace.weekly_report import scoring_llm


class BytesForKieShrinkTest(unittest.TestCase):
    def setUp(self):
        from ecentric_workspace.weekly_report import sharepoint
        self._sp = sharepoint
        # Va vao module ma scoring_llm DANG tro toi, khong phai ban tu import:
        # bo test test_scoring_llm co luc gan de `scoring_llm.gemini_api` bang
        # stub, nen hai cai co the KHAC nhau tuy thu tu chay. Va nham = test
        # xanh gia vi no do ham that chu khong do ham minh dat vao.
        self.G = scoring_llm.gemini_api
        self._fetch = self.G.fetch_pdf_bytes
        self._shrink = self.G.shrink_pdf_for_inline
        self._max = scoring_llm.MAX_INLINE_TOTAL
        self._token = sharepoint.get_app_token
        # Thay tren CHINH module that: `_bytes_for_kie` dung
        # `from ... import sharepoint`, tuc lay thuoc tinh da gan tren package --
        # doi sys.modules khong an thua (da thu, 5 test do).
        sharepoint.get_app_token = lambda: "TOKEN"

    def tearDown(self):
        self.G.fetch_pdf_bytes = self._fetch
        self.G.shrink_pdf_for_inline = self._shrink
        scoring_llm.MAX_INLINE_TOTAL = self._max
        self._sp.get_app_token = self._token

    def _serve(self, sizes):
        blobs = [b"%PDF" + b"x" * (n - 4) for n in sizes]
        seq = list(blobs)

        def fake(url, token, dept):
            b = seq.pop(0)
            return {"ok": True, "data": b, "size_bytes": len(b),
                    "display_name": "d.pdf"}
        self.G.fetch_pdf_bytes = fake

    def test_under_limit_never_calls_shrink(self):
        scoring_llm.MAX_INLINE_TOTAL = 1000
        self._serve([300, 300])
        called = []
        self.G.shrink_pdf_for_inline = lambda *a, **k: called.append(1) or (None, "x")
        files, why = scoring_llm._bytes_for_kie(["u1", "u2"], "Svc")
        self.assertEqual(why, "")
        self.assertEqual(len(files), 2)
        self.assertEqual(called, [], "duoi tran thi khong duoc dung toi nen")

    def test_over_limit_shrinks_and_keeps_all_files(self):
        scoring_llm.MAX_INLINE_TOTAL = 1000
        self._serve([400, 900])
        self.G.shrink_pdf_for_inline = lambda data, max_bytes=None: (
            b"%PDF" + b"y" * 396, "da nen")
        files, why = scoring_llm._bytes_for_kie(["u1", "u2"], "Svc")
        self.assertEqual(why, "")
        self.assertEqual(len(files), 2, "phai giu DU tep, khong duoc bo bot")
        self.assertEqual(len(files[1]["data"]), 400)

    def test_shrink_fails_gives_up_whole_batch(self):
        """Khong nen duoc => ([], ly_do). Tuyet doi khong gui mot phan deck."""
        scoring_llm.MAX_INLINE_TOTAL = 1000
        self._serve([400, 900])
        self.G.shrink_pdf_for_inline = lambda data, max_bytes=None: (None, "qua san")
        files, why = scoring_llm._bytes_for_kie(["u1", "u2"], "Svc")
        self.assertEqual(files, [])
        self.assertIn("qua san", why)

    def test_download_failure_still_gives_up_whole_batch(self):
        """Nhanh nen KHONG duoc lam yeu ky luat cu."""
        scoring_llm.MAX_INLINE_TOTAL = 10000
        self.G.fetch_pdf_bytes = lambda url, token, dept: {
            "ok": False, "error": "Graph 404 itemNotFound"}
        files, why = scoring_llm._bytes_for_kie(["u1"], "Svc")
        self.assertEqual(files, [])
        self.assertIn("404", why)

    def test_shrink_budget_accounts_for_files_already_taken(self):
        """Tran truyen cho shrink phai la phan CON LAI, khong phai tran tong."""
        scoring_llm.MAX_INLINE_TOTAL = 1000
        self._serve([700, 500])
        seen = {}

        def fake_shrink(data, max_bytes=None):
            seen["max_bytes"] = max_bytes
            return b"%PDF" + b"z" * 96, "ok"
        self.G.shrink_pdf_for_inline = fake_shrink
        files, why = scoring_llm._bytes_for_kie(["u1", "u2"], "Svc")
        self.assertEqual(why, "")
        self.assertEqual(seen["max_bytes"], 300,
                         "con 300 byte sau khi tep dau chiem 700")


class ShrinkGuardTest(unittest.TestCase):
    def test_returns_input_untouched_when_already_small(self):
        data = b"%PDF" + b"a" * 100
        out, note = gemini_api.shrink_pdf_for_inline(data, max_bytes=1000)
        self.assertIs(out, data)
        self.assertEqual(note, "")

    def test_empty_input_is_refused(self):
        out, note = gemini_api.shrink_pdf_for_inline(b"", max_bytes=10)
        self.assertIsNone(out)

    def test_floor_is_half_scale(self):
        """San chat luong la mot quyet dinh, khong phai con so tuy tien:
        ha them nua thi slide mo den muc model doc sai ma van cham diem."""
        self.assertEqual(gemini_api.SHRINK_MIN_SCALE, 0.5)
        self.assertTrue(all(s >= gemini_api.SHRINK_MIN_SCALE
                            for s, _q in gemini_api.SHRINK_STEPS))

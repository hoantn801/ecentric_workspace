# Copyright (c) 2026, eCentric and contributors
"""Dem tep phai dem thu THUC SU vao request, khong phai thu chuan bi duoc.

SU CO 25/09, ban ghi that: WTU-2026-W39-NV00162 nhan 17/100.
  1. Kie tai duoc 1 PDF -> files = [{data: <bytes>, uri: None}]
  2. _call_kie TIMEOUT -> roi ve Google
  3. nhanh Google chi nhan phan tu co `uri`, bo qua phan tu chi co bytes
     -> google_parts RONG -> Google duoc goi KHONG kem tep nao
  4. model cham tren moi phan text cua form -> 17/100, ghi vao ho so

Chot chan dau tien kiem `files_sent = len(files)` = 1 nen CHO QUA. No do "da tai
duoc bao nhieu tep", trong khi rui ro no tuyen bo la "model co nhin thay slide
khong". Cong do sai dai luong thi vo dung.

Bo test nay khoa ca hai dau: generate_json phai TU CHOI goi, va scoring phai TU
CHOI ghi diem.
"""

import unittest

from ecentric_workspace import gemini_api
from ecentric_workspace.weekly_report import scoring


class GenerateJsonRefusesWhenNoFileUsable(unittest.TestCase):
    """Co tep can gui ma khong tep nao dung duoc => KHONG goi nha cung cap."""

    def setUp(self):
        self._provider = gemini_api.provider
        self._call_google = gemini_api._call_google
        self._call_kie = gemini_api._call_kie
        self.google_calls = []

        def spy_google(body, model, timeout):
            self.google_calls.append(body)
            return '{"overall_score": 17}', ""
        gemini_api._call_google = spy_google
        gemini_api._call_kie = lambda body, timeout: ("", "ReadTimeout")
        gemini_api.provider = lambda: gemini_api.KIE_PROVIDER

    def tearDown(self):
        gemini_api.provider = self._provider
        gemini_api._call_google = self._call_google
        gemini_api._call_kie = self._call_kie

    def test_bytes_only_file_does_not_silently_call_google_without_it(self):
        """Dung kich ban da xay ra that: bytes co, uri khong, Kie timeout."""
        res = gemini_api.generate_json(
            "prompt", {"type": "object"},
            files=[{"data": b"%PDF123", "mime_type": "application/pdf"}])
        self.assertFalse(res["ok"], "phai tu choi, khong duoc tra diem")
        self.assertEqual(res["files_in_request"], 0)
        self.assertEqual(self.google_calls, [],
                         "KHONG duoc goi Google khi khong tep nao gui duoc")
        self.assertIn("khong tep nao dung duoc", res["error"])

    def test_file_with_uri_still_reaches_google(self):
        res = gemini_api.generate_json(
            "prompt", {"type": "object"},
            files=[{"uri": "files/abc", "mime_type": "application/pdf"}])
        self.assertTrue(res["ok"])
        self.assertEqual(res["files_in_request"], 1)
        self.assertEqual(len(self.google_calls), 1)

    def test_no_files_at_all_is_allowed(self):
        """Prompt thuan text (vi du AI dien ho) khong bi chan."""
        res = gemini_api.generate_json("prompt", {"type": "object"}, files=None)
        self.assertTrue(res["ok"])
        self.assertEqual(res["files_in_request"], 0)

    def test_counts_only_the_files_that_actually_went(self):
        """Mot tep co uri, mot tep chi co bytes => DUNG 1 tep vao request.

        Them sau khi dot bien M2 (`files_in_request = len(files)`) SONG SOT: bo
        test cu khong co ca nao ma so tep chuan bi KHAC so tep gui duoc, nen hai
        cach dem cho ket qua giong nhau va phep do khong phan biet duoc. Day dung
        la kieu sai da gay ra su co 25/09, chi khac o cho no an mot tang sau.
        """
        res = gemini_api.generate_json(
            "prompt", {"type": "object"},
            files=[{"uri": "files/abc", "mime_type": "application/pdf"},
                   {"data": b"%PDF123", "mime_type": "application/pdf"}])
        self.assertTrue(res["ok"])
        self.assertEqual(res["files_in_request"], 1,
                         "chi 1 tep co uri nen chi 1 tep vao duoc request")
        self.assertEqual(len(self.google_calls), 1)
        parts = self.google_calls[0]["contents"][0]["parts"]
        file_parts = [p for p in parts if "fileData" in p]
        self.assertEqual(len(file_parts), 1)


class ScoringRefusesOnZeroFilesInRequest(unittest.TestCase):
    def test_prepared_but_not_sent_is_refused(self):
        """1 tep tai duoc, 0 tep vao request => tu choi, va noi ro ca hai so."""
        res = {"ok": True, "data": {"overall_score": 17},
               "files_prepared": 1, "files_sent": 0,
               "kie_skipped": "", "error": "ReadTimeout"}
        out = scoring._assert_deck_reached_model(res, "WTU-2026-W39-NV00162")
        self.assertIsNotNone(out)
        self.assertFalse(out["success"])
        self.assertIn("da tai duoc 1 tep", out["error"])
        self.assertIn("KHONG tep nao vao duoc request", out["error"])

    def test_sent_is_what_counts_not_prepared(self):
        res = {"ok": True, "data": {}, "files_prepared": 3, "files_sent": 3}
        self.assertIsNone(scoring._assert_deck_reached_model(res, "WTU-X"))

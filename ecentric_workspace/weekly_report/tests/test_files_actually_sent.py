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
    """Co tep can gui ma khong tep nao gui du duoc => KHONG goi AI.

    28/09: cong AI chung (platform/ai) thay Kie+Google. Khong con URI Google - tep
    phai mang bytes, va mot tep thieu bytes lam CA LAN GOI bi tu choi. Do thang vao
    transport cua cong (`gateway._post`) de biet chac khong co request nao di ra.
    """

    def setUp(self):
        from ecentric_workspace.platform.ai import config, gateway
        self.gw, self.cfg = gateway, config
        self._post, self._key = gateway._post, config.api_key
        self.calls = []

        def spy(url, body, key, timeout):
            self.calls.append(body)
            return 200, "data: " + '{"candidates":[{"content":{"parts":[{"text":"{\\"overall_score\\": 17}"}]}}]}'
        gateway._post = spy
        config.api_key = lambda: "KHOA-GIA"

    def tearDown(self):
        self.gw._post, self.cfg.api_key = self._post, self._key

    def test_file_without_bytes_is_refused_before_any_call(self):
        res = gemini_api.generate_json(
            "prompt", {"type": "object"},
            files=[{"uri": "files/abc", "mime_type": "application/pdf"}])
        self.assertFalse(res["ok"])
        self.assertEqual(res["files_in_request"], 0)
        self.assertEqual(self.calls, [], "KHONG duoc goi AI khi co tep thieu bytes")

    def test_one_file_missing_bytes_refuses_all(self):
        res = gemini_api.generate_json(
            "prompt", {"type": "object"},
            files=[{"data": b"%PDF123", "mime_type": "application/pdf"},
                   {"uri": "files/abc", "mime_type": "application/pdf"}])
        self.assertFalse(res["ok"])
        self.assertEqual(self.calls, [], "khong duoc gui 1 tep khi nguoi goi co 2")

    def test_no_files_at_all_is_allowed(self):
        """Prompt thuan text (vi du AI dien ho) khong bi chan."""
        res = gemini_api.generate_json("prompt", {"type": "object"}, files=None)
        self.assertTrue(res["ok"])
        self.assertEqual(res["files_in_request"], 0)

    def test_counts_the_files_that_actually_went(self):
        res = gemini_api.generate_json(
            "prompt", {"type": "object"},
            files=[{"data": b"%PDF1", "mime_type": "application/pdf"},
                   {"data": b"%PDF2", "mime_type": "application/pdf"}])
        self.assertTrue(res["ok"])
        self.assertEqual(res["files_in_request"], 2)
        parts = self.calls[0]["contents"][-1]["parts"]
        self.assertEqual(len([p for p in parts if "inlineData" in p]), 2)


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

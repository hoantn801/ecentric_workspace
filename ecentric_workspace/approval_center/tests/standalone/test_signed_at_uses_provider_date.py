# Copyright (c) 2026, eCentric and contributors
"""Use the date the provider sends. Do not infer it.

eContract returns `date` AND `time` as separate fields on every signer row. We read only
`time` - a bare clock like "11:48" - and then built a heuristic to guess which day it
belonged to, resolving it against the moment we asked for the signature.

On 2026-08-28 that guess was about to produce a wrong answer on a real document. Phuong
signed at 11:48 today; the request had been queued at 23:23 yesterday. Resolving "11:48"
against a reference of 23:23-yesterday picks YESTERDAY 11:48 - eleven hours before the
request - and the leg would have been refused as "signature predates request", for a
signature that is perfectly valid.

Two nights of work went into that heuristic while the provider was sending the date on the
very next field. The rule this encodes: when the source states a fact, do not derive it.
"""
import sys
import types
import unittest


def _stub_frappe():
    """providers/scts.py nhap frappe o cap module. Stub toi thieu chi de nhap duoc; moi phep
    kiem duoi day deu la ham thuan, khong cham DB."""
    if "frappe" in sys.modules:
        return
    fr = types.ModuleType("frappe")
    fr.db = types.SimpleNamespace(get_value=lambda *a, **k: None, get_all=lambda *a, **k: [])
    fr.get_all = lambda *a, **k: []
    fr.get_doc = lambda *a, **k: None
    fr.throw = lambda *a, **k: (_ for _ in ()).throw(Exception("throw"))
    fr.log_error = lambda *a, **k: None
    fr._ = lambda x: x
    fr.utils = types.ModuleType("frappe.utils")
    fr.utils.now_datetime = lambda: None
    fr.utils.add_to_date = lambda *a, **k: None
    fr.utils.get_datetime = lambda *a, **k: None
    fr.utils.cint = int
    fr.utils.flt = float
    fr.utils.__path__ = []                      # coi frappe.utils la mot goi, de co module con
    pw = types.ModuleType("frappe.utils.password")
    pw.get_decrypted_password = lambda *a, **k: ""
    fr.utils.password = pw
    sys.modules["frappe.utils.password"] = pw
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = fr.utils


_stub_frappe()

from ecentric_workspace.platform.esign.providers.scts import SctsAdapter   # noqa: E402


class TestSignedAtCombinesDateAndTime(unittest.TestCase):
    def test_date_and_time_are_joined(self):
        self.assertEqual(
            SctsAdapter._signed_at({"date": "28/08/2026", "time": "11:48"}),
            "28/08/2026 11:48")

    def test_result_is_parseable_without_any_guessing(self):
        from ecentric_workspace.platform.esign.providers.base import SignatureProviderAdapter
        got = SignatureProviderAdapter._parse_provider_time(
            SctsAdapter._signed_at({"date": "28/08/2026", "time": "11:48:20"}))
        self.assertIsNotNone(got, "ghep xong phai doc duoc ma KHONG can moc tham chieu")
        self.assertEqual((got.day, got.month, got.year, got.hour, got.minute),
                         (28, 8, 2026, 11, 48))

    def test_an_explicit_timestamp_still_wins(self):
        self.assertEqual(
            SctsAdapter._signed_at({"signedAt": "2026-08-28T11:48:20", "date": "01/01/2000",
                                    "time": "00:00"}),
            "2026-08-28T11:48:20")

    def test_time_alone_still_works_when_there_is_no_date(self):
        self.assertEqual(SctsAdapter._signed_at({"time": "11:48"}), "11:48")

    def test_unsigned_rows_report_nothing(self):
        for row in ({"time": "Chưa có", "date": "28/08/2026"}, {"time": ""}, {}):
            self.assertIsNone(SctsAdapter._signed_at(row))

    def test_a_placeholder_date_is_not_glued_on(self):
        self.assertEqual(SctsAdapter._signed_at({"date": "Chưa có", "time": "11:48"}), "11:48")


class TestTheRealCaseThatWouldHaveBeenRejected(unittest.TestCase):
    """Tai hien dung tinh huong that ngay 28/08."""

    def test_yesterdays_request_accepts_todays_signature(self):
        from datetime import datetime, timedelta
        from ecentric_workspace.platform.esign.providers.base import SignatureProviderAdapter as A

        asked = datetime(2026, 8, 27, 23, 23, 24)          # xep hang dem qua
        signed = SctsAdapter._signed_at({"date": "28/08/2026", "time": "11:48:20"})
        got = A._parse_provider_time(signed, reference=asked - timedelta(seconds=120))
        self.assertGreater(got, asked, "chu ky hom nay phai duoc coi la SAU yeu cau dem qua")

    def test_the_bare_clock_alone_would_have_been_rejected(self):
        """Nghiem thu nguoc: khong co ngay thi chinh heuristic cua minh se tu choi nham."""
        from datetime import datetime, timedelta
        from ecentric_workspace.platform.esign.providers.base import SignatureProviderAdapter as A

        asked = datetime(2026, 8, 27, 23, 23, 24)
        got = A._parse_provider_time("11:48:20", reference=asked - timedelta(seconds=120))
        self.assertLess(got, asked,
                        "day chinh la ket qua sai ma viec ghep ngay da loai bo")


if __name__ == "__main__":
    unittest.main()

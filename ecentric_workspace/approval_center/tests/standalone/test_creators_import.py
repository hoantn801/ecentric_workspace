# Copyright (c) 2026, eCentric and contributors
"""Nhap creator tu sheet cu (11/11/2026) - chay khong can bench.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_creators_import.py
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "..", "..")))

from test_creators_service import EXISTING, FakeRepo  # noqa: E402

from ecentric_workspace.approval_center.shared.creators import import_service  # noqa: E402
from ecentric_workspace.approval_center.shared.creators.service import (  # noqa: E402
    CreatorPermissionError, CreatorService)

FIN = {"ketoan@ec": ["EC Finance"]}


def svc():
    return CreatorService(FakeRepo([EXISTING], roles=FIN))


ROW_OK = {"Họ tên": "Trần Văn B", "Loại": "cá nhân", "CCCD": "001 202 303 404",
          "Ngày sinh": "02/03/1999", "Số tài khoản": "1234-5678-9", "Ngân hàng": "VCB",
          "TikTok ID": "@tranb", "Mã viết tắt": "tvb"}


class ImportTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        s = svc()
        out = import_service.import_rows("ketoan@ec", [ROW_OK], apply=False, service=s)
        self.assertEqual((out["would_create"], out["created"]), (1, 0))
        self.assertEqual(s.repo.inserted, [])
        self.assertEqual(out["rows"][0]["line"], 2)

    def test_apply_creates_with_normalized_values(self):
        s = svc()
        out = import_service.import_rows("ketoan@ec", [ROW_OK], apply=True, service=s)
        self.assertEqual(out["created"], 1)
        row = s.repo.inserted[0]
        self.assertEqual(row["ec_cr_cccd"], "001202303404")
        self.assertEqual(row["ec_bank_account_no"], "123456789")
        self.assertEqual(row["ec_cr_dob"], "1999-03-02")
        self.assertEqual(row["ec_cr_party_code"], "TVB")
        self.assertEqual(row["ec_cr_type"], "Cá nhân")
        self.assertEqual(row["supplier_group"], "KOL/KOC Creator")

    def test_hard_duplicate_against_erp_skipped(self):
        dup = dict(ROW_OK, CCCD="079123456789")
        out = import_service.import_rows("ketoan@ec", [dup], apply=True, service=svc())
        self.assertEqual((out["duplicate"], out["created"]), (1, 0))
        self.assertEqual(out["rows"][0]["existing"], "SUP-001")
        self.assertEqual(out["rows"][0]["matched"], ["CCCD"])

    def test_duplicate_inside_file_caught_in_dry_run(self):
        out = import_service.import_rows("ketoan@ec", [ROW_OK, dict(ROW_OK)], service=svc())
        self.assertEqual((out["would_create"], out["duplicate"]), (1, 1))

    def test_soft_duplicate_created_with_ack(self):
        s = svc()
        row = dict(ROW_OK, **{"Họ tên": "nguyen thi hao"})
        out = import_service.import_rows("ketoan@ec", [row], apply=True, service=s)
        self.assertEqual((out["created"], out["soft_duplicate"]), (1, 1))
        self.assertIn("Nguyễn Thị Hảo", s.repo.inserted[0]["ec_cr_dup_ack"])

    def test_errors_reported_not_raised(self):
        bad = [{"Họ tên": "X", "Loại": "cá nhân"}, dict(ROW_OK, **{"Ngày sinh": "abc"})]
        out = import_service.import_rows("ketoan@ec", bad, service=svc())
        self.assertEqual(out["errors"], 2)
        self.assertIn("CCCD", out["rows"][0]["message"])

    def test_misa_code_unique(self):
        row = dict(ROW_OK, **{"Mã khách hàng": "KH0001"})
        out = import_service.import_rows("ketoan@ec", [row], service=svc())
        self.assertEqual(out["errors"], 1)

    def test_only_finance(self):
        with self.assertRaises(CreatorPermissionError):
            import_service.import_rows("sale@ec", [ROW_OK], service=svc())

    def test_result_has_no_pii(self):
        out = import_service.import_rows("ketoan@ec", [ROW_OK], service=svc())
        text = repr(out)
        self.assertNotIn("001202303404", text)
        self.assertNotIn("123456789", text)

    def test_unmapped_headers_listed(self):
        row = dict(ROW_OK, **{"Cột lạ": "x", "STT": "1"})
        out = import_service.import_rows("ketoan@ec", [row], service=svc())
        self.assertEqual(out["unmapped_headers"], ["Cột lạ"])


if __name__ == "__main__":
    unittest.main()

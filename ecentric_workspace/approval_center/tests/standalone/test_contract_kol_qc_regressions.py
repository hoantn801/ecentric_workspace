# Copyright (c) 2026, eCentric and contributors
"""Hop dong KOL/KOC - khoa cac loi QC 11/11/2026 tim ra truoc deploy (khong can bench).

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_contract_kol_qc_regressions.py

Moi test ung voi mot loi that da sua: neu test do lai, loi do da quay ve.
"""
import datetime as dt
import importlib.util
import os
import pathlib
import sys
import types
import unittest

_HERE = pathlib.Path(__file__).resolve().parent
AC = _HERE.parents[1]
sys.path.insert(0, str(AC.parent.parent))
sys.path.insert(0, str(_HERE))

from test_contract_kol_domain import doc_xml, make_docx  # noqa: E402

from ecentric_workspace.approval_center.features.contract_review.domain import docx_fill, kol  # noqa: E402
from ecentric_workspace.approval_center.shared.creators import domain as cdomain  # noqa: E402


class MoneyGuards(unittest.TestCase):
    def test_thue_suat_ngoai_khoang_bi_tu_choi_khong_chia_0(self):
        for rate in (100, 150, -20, "abc"):
            with self.assertRaises(ValueError):
                kol.compute_amounts("Cá nhân", kol.NET_AFTER_PIT, 10_000_000, pit_rate=rate)
        with self.assertRaises(ValueError):
            kol.compute_amounts("Công ty", kol.WITH_VAT, 10_000_000, vat_rate=-100)

    def test_so_tien_inf_nan_chu(self):
        for v in ("inf", "nan", "mười triệu", 1e15):
            with self.assertRaises(ValueError):
                kol.compute_amounts("Cá nhân", kol.GROSS_BEFORE_PIT, v)

    def test_lam_tron_nua_len_khong_kieu_ngan_hang(self):
        a = kol.compute_amounts("Cá nhân", kol.GROSS_BEFORE_PIT, 1_000_005)
        b = kol.compute_amounts("Cá nhân", kol.GROSS_BEFORE_PIT, 1_000_015)
        self.assertEqual(a["pit"], 100_001)
        self.assertEqual(b["pit"], 100_002)

    def test_ty_le_coc_chi_trong_danh_sach(self):
        self.assertEqual(kol.advance_amount(10_000_000, kol.PAY_ADVANCE, "30"), 3_000_000)
        for pct in (33, 99, 0):
            with self.assertRaises(ValueError):
                kol.advance_amount(10_000_000, kol.PAY_ADVANCE, pct)

    def test_so_ngay_thanh_toan_0_hop_le_am_bi_chan(self):
        fri = dt.date(2026, 11, 13)
        self.assertEqual(kol.due_date(dt.date(2026, 11, 12), 0), dt.date(2026, 11, 12))
        self.assertEqual(kol.due_date(fri, None), dt.date(2026, 12, 14))  # 13/12 la CN -> T2
        with self.assertRaises(ValueError):
            kol.due_date(fri, -10)


class NumberAndPlaceholders(unittest.TestCase):
    def test_so_hop_dong_con_khop_hay_phai_cap_lai(self):
        base = kol.number_base("2026-11-11", "ntp", "fcv")
        self.assertTrue(kol.number_fits(base, base))
        self.assertTrue(kol.number_fits(base + "-2", base))
        self.assertFalse(kol.number_fits("11112026/HDDV/ECENTRIC-ABC.FCV", base))
        self.assertFalse(kol.number_fits(None, base))

    def test_truong_bat_buoc_rong_bi_bao_thieu(self):
        vals = kol.placeholders({"contract_no": "X", "contract_date": "2026-11-11"},
                                {"supplier_name": "A", "ec_cr_type": "Cá nhân"})
        miss = kol.empty_required(vals, ["ten_creator", "cccd", "so_tai_khoan", "tiktok_id"], "Cá nhân")
        self.assertEqual(sorted(miss), ["cccd", "so_tai_khoan"])   # tiktok_id rong la binh thuong

    def test_mau_hop_dong_dung_khoa_bbnt_la_khoa_la(self):
        self.assertNotIn("so_tien_nghiem_thu", kol.known_placeholders(False))
        self.assertIn("so_tien_nghiem_thu", kol.known_placeholders(True))

    def test_thue_suat_mac_dinh_khi_phieu_chua_co(self):
        vals = kol.placeholders({}, {})
        self.assertEqual(vals["thue_suat_tncn"], "10%")
        self.assertEqual(vals["so_ngay_thanh_toan"], "30")


class DocxEdges(unittest.TestCase):
    def test_ten_sai_khuon_bi_bao_khong_bo_sot(self):
        _out, missing = docx_fill.fill_docx(make_docx('<w:p><w:r><w:t>{{tên}} {{ten-creator}}</w:t></w:r></w:p>'), {})
        self.assertIn("{{tên}}", missing)
        self.assertIn("{{ten-creator}}", missing)

    def test_dau_ngoac_kep_khong_bi_escape_hai_lan(self):
        body = '<w:p><w:r><w:t>&quot;Bên B&quot;: {{ten_creator}}</w:t></w:r></w:p>'
        out, _m = docx_fill.fill_docx(make_docx(body), {"ten_creator": "A"})
        self.assertNotIn("&amp;quot;", doc_xml(out))

    def test_w_t_tu_dong_khong_lam_hong_doan(self):
        body = ('<w:p><w:r><w:t xml:space="preserve"/></w:r><w:r><w:t>{{ten_creator}}</w:t></w:r>'
                '<w:r><w:t>đuôi</w:t></w:r></w:p>')
        out, _m = docx_fill.fill_docx(make_docx(body), {"ten_creator": "A"})
        xml = doc_xml(out)
        self.assertIn('<w:t xml:space="preserve"/>', xml)
        self.assertIn("<w:t>A</w:t>", xml)
        self.assertIn("<w:t>đuôi</w:t>", xml)

    def test_placeholder_sau_khung_van_ban_bi_bao_khong_lot_qua(self):
        body = ('<w:p><w:r><w:t>A {{ten_creator}}</w:t></w:r><w:r><w:pict><w:txbxContent><w:p><w:r>'
                '<w:t>box {{cccd}}</w:t></w:r></w:p></w:txbxContent></w:pict></w:r>'
                '<w:r><w:t>sau {{dia_chi}}</w:t></w:r></w:p>')
        _out, missing = docx_fill.fill_docx(make_docx(body), {"ten_creator": "X", "cccd": "1", "dia_chi": "Y"})
        self.assertEqual(missing, ["{{dia_chi}} (không điền được)"])

    def test_dia_chi_nhieu_dong_thanh_xuong_dong_word(self):
        out, _m = docx_fill.fill_docx(make_docx('<w:p><w:r><w:t>{{dia_chi}}</w:t></w:r></w:p>'),
                                      {"dia_chi": "Số 1\nQuận 1"})
        self.assertIn("<w:br/>", doc_xml(out))


class CreatorDedupe(unittest.TestCase):
    def test_link_tiktok_co_dau_gach_va_query(self):
        for v in ("https://www.tiktok.com/@abc/", "https://www.tiktok.com/@ABC?lang=vi", "@abc"):
            self.assertEqual(cdomain._handle(v), "abc")

    def test_so_dien_thoai_0084_va_0_trong_ngoac(self):
        for v in ("0084912345678", "+84 (0)912 345 678", "84912345678", "0912 345 678"):
            self.assertEqual(cdomain._phone(v), "0912345678")

    def test_cccd_trung_mst_ca_nhan_cua_ban_ghi_khac_la_trung_cung(self):
        dup = cdomain.classify_duplicates({"ec_cr_cccd": "079123456789"},
                                          [{"name": "S1", "supplier_name": "x", "tax_id": "079123456789"}])
        self.assertEqual([m["name"] for m in dup["hard"]], ["S1"])

    def test_email_sai_va_truong_qua_dai_bi_chan_truoc_khi_ghi(self):
        errs = cdomain.validate_payload({"supplier_name": "a", "ec_cr_type": "Cá nhân",
                                         "ec_cr_cccd": "079123456789", "ec_cr_email": "bad",
                                         "ec_cr_channel_url": "x" * 200})
        self.assertTrue(any("Email" in e for e in errs))
        self.assertTrue(any("140" in e for e in errs))


def _fake_frappe(rows_by_call):
    fake = types.ModuleType("frappe")
    fake._ = lambda s: s
    fake.session = types.SimpleNamespace(user="sale@ec")
    calls = []

    def get_all(dt_, filters=None, or_filters=None, fields=None, pluck=None, **k):
        calls.append((dt_, dict(filters or {})))
        rows = rows_by_call(dt_, filters or {})
        return [r[pluck] for r in rows] if pluck else [_Row(r) for r in rows]
    fake.get_all = get_all
    fake.get_roles = lambda u=None: []
    fake.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
    fake._calls = calls
    return fake


class _Row(dict):
    __getattr__ = dict.get


class SoSearch(unittest.TestCase):
    """Loi chan deploy: `_gbs_owners` khong ton tai -> nhan vien thuong (khong phai ke toan)
    tim SO la NameError, khong tao duoc hop dong KOL nao."""

    def _load(self, fake):
        sys.modules["frappe"] = fake
        try:
            path = AC / "features/contract_review/application/kol_lookup.py"
            spec = importlib.util.spec_from_file_location("kol_lookup_qc", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        finally:
            sys.modules.pop("frappe", None)

    def test_nhan_vien_thuong_tim_so_khong_loi_va_loc_team_trong_truy_van(self):
        so = [{"name": "SO-1", "owner": "sale@ec", "ec_channel": "Direct", "transaction_date": "2026-11-01"},
              {"name": "SO-2", "owner": "x@ec", "ec_channel": "GBS", "ec_gbs_so_ref": "GBS-9",
               "transaction_date": "2026-11-05"}]

        def rows(dt_, f):
            if dt_ == "Employee":
                return [{"user_id": "sale@ec"}]
            if dt_ == "GBS Sales Order":
                return [{"name": "GBS-9"}]
            if dt_ == "Sales Order":
                if "owner" in f:
                    return [r for r in so if r["owner"] in f["owner"][1]]
                if "ec_gbs_so_ref" in f:
                    return [r for r in so if r.get("ec_gbs_so_ref") in f["ec_gbs_so_ref"][1]]
            return []
        fake = _fake_frappe(rows)
        fake.db = types.SimpleNamespace(get_value=lambda *a, **k: "Sales - EC")
        mod = self._load(fake)
        out = mod.search_sales_orders("sale@ec", "")
        self.assertEqual([r["value"] for r in out], ["SO-2", "SO-1"])   # moi nhat truoc
        so_queries = [f for d, f in fake._calls if d == "Sales Order"]
        self.assertTrue(all("owner" in f or "ec_gbs_so_ref" in f for f in so_queries))


if __name__ == "__main__":
    unittest.main()

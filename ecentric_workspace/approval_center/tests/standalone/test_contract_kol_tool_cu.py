# Copyright (c) 2026, eCentric and contributors
"""Doi chieu ERP voi tool Google Sheet cu (anh Hoan 12/11: dung lai 18 mau cua Ke toan).

Chay TRUC TIEP code JS goc cua tool cu (fixtures/tool_cu_hddv_v503.js, trich nguyen van tu Apps
Script V5.0.3) bang node, roi so voi ban port Python tren cung bo dau vao: cau chu dien vao hop
dong, so tien, chu so, ma doi tac, ngay ky phai GIONG HET. Khong co node thi bo qua (CI co node).

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_contract_kol_tool_cu.py
"""
import datetime as dt
import json
import os
import random
import shutil
import subprocess
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "..", "..")))

from ecentric_workspace.approval_center.features.contract_review.domain import (  # noqa: E402
    kol, kol_texts as T, vn_words)
from ecentric_workspace.approval_center.features.contract_review.domain.kol_work_texts import (  # noqa: E402
    advance_texts, work_texts)

JS = os.path.join(_HERE, "fixtures", "tool_cu_hddv_v503.js")
TYPE = {"PERSON": "Cá nhân", "COMPANY": "Công ty", "HOUSEHOLD": "Hộ kinh doanh"}
AMOUNT = {"NET_AFTER_TNCN": kol.NET_AFTER_PIT, "GROSS_BEFORE_TNCN": kol.GROSS_BEFORE_PIT,
          "BEFORE_VAT": kol.BEFORE_VAT, "AFTER_VAT": kol.WITH_VAT,
          "TOTAL_INCLUDED_HOUSEHOLD_TAX": kol.HOUSEHOLD_TOTAL}


def _cases():
    rnd = random.Random(20261112)
    work = []
    for kind in ("LIVESTREAM", "VIDEO", "HYBRID"):
        for dur in ("", "60 phút"):
            for custom in ("", "Quay tại studio"):
                work.append({"kind": kind, "brand": "Vinasoy & Co", "url": "https://www.tiktok.com/@abc",
                             "dates": ["2026-12-05", "2026-12-12"], "q": rnd.choice([1, 2, 9, 10, 12]),
                             "dur": dur, "custom": custom, "platform": "TikTok"})
    work.append({"kind": "LIVESTREAM", "brand": "FCV", "url": "https://shopee.vn/abc", "dates": ["2026-12-05"],
                 "q": 3, "dur": "", "custom": "", "platform": "Shopee"})
    numbers = [0, 1, 5, 10, 14, 15, 21, 24, 25, 101, 105, 110, 1_000, 1_005_000, 1_050_000, 24_000,
               1_000_000_000, 1_005_000_000, 2_000_000_000_001, 999_999_999]
    numbers += [rnd.randrange(1, 5_000_000_000) for _ in range(300)]
    calc = []
    for _ in range(400):
        t = rnd.choice(list(TYPE))
        at = {"PERSON": ["NET_AFTER_TNCN", "GROSS_BEFORE_TNCN"], "COMPANY": ["BEFORE_VAT", "AFTER_VAT"],
              "HOUSEHOLD": ["TOTAL_INCLUDED_HOUSEHOLD_TAX"]}[t]
        calc.append({"type": t, "amount": rnd.randrange(100_000, 200_000_000) + rnd.choice([0, 0.5, 0.25]),
                     "amountType": rnd.choice(at), "tnc": 0.10, "vat": rnd.choice([0.08, 0.10, 0.05])})
    party = [{"type": t, "name": n, "manual": m}
             for t in TYPE for n in ("Nguyễn Thị Phương", "CÔNG TY TNHH THƯƠNG MẠI DỊCH VỤ ABC",
                                     "Hộ kinh doanh - Bánh Mì Đức", "Công ty Cổ phần Ecentric", "Lê A")
             for m in ("", "ntp", "HKD", "CONGTY", "ABCDEFGHI")]
    bank = [["Vietcombank", ""], ["Vietcombank", "Hà Nội"], ["ACB", "CN Tân Bình"], [" TCB ", "chi nhánh Q1"]]
    addr = ["", "12 Lê Lợi, Q1, TP.HCM", "12 Lê Lợi ,, Q1 ,  HCM.", "Hà Nội, Việt Nam", "1 A, Viet Nam,"]
    honor = ["Ông Nguyễn Văn A", "bà Lê B", "Anh C", "Chị D", "Nguyễn E"]
    holidays = ["2026-01-01", "2026-04-30", "2026-05-01", "2026-09-02"]
    dates = []
    for boundary in ("2026-05-04", "2026-05-02", "2026-09-03", "2026-12-07", "2026-11-12"):
        for inp in (None, "2026-04-29", "2026-12-25"):
            for n in (1, 2):
                dates.append({"input": inp, "boundary": boundary, "n": n})
    return {"work": work, "numbers": numbers, "calc": calc, "party": party, "bank": bank, "addr": addr,
            "honor": honor, "holidays": holidays, "dates": dates}


def _d(s):
    return dt.date.fromisoformat(s) if s else None


@unittest.skipUnless(shutil.which("node"), "can node de chay code goc cua tool cu")
class GiongToolCu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = _cases()
        res = subprocess.run(["node", JS], input=json.dumps(cls.case), capture_output=True, text=True, timeout=60)
        if res.returncode:
            raise RuntimeError(res.stderr)
        cls.js = json.loads(res.stdout)

    def test_doan_van_cong_viec(self):
        for c, want in zip(self.case["work"], self.js["work"]):
            dates = [_d(x) for x in c["dates"]]
            got = work_texts(c["kind"], c["brand"], c["url"], dates, c["q"], c["dur"], c["custom"],
                             c["platform"] == "Shopee")
            self.assertEqual(got, want, c)

    def test_doan_van_mau_co_coc(self):
        tiktok = [c for c in self.case["work"] if c["platform"] != "Shopee"]
        for c, want in zip(tiktok, self.js["adv"]):
            dates = [_d(x) for x in c["dates"]]
            got = advance_texts(c["kind"], c["brand"], c["url"], dates, c["q"], c["dur"], c["custom"])
            self.assertEqual(got, want, c)

    def test_so_tien_bang_chu_va_dinh_dang(self):
        for n, words, money in zip(self.case["numbers"], self.js["words"], self.js["money"]):
            if n == 0:
                continue  # hop dong khong co dong 0 (tool cu: "Không đồng", ERP khong dien)
            self.assertEqual(vn_words.amount_in_words(n), words, n)
            self.assertEqual(T.money(n), money, n)

    def test_tinh_tien(self):
        for c, want in zip(self.case["calc"], self.js["calc"]):
            ctype = TYPE[c["type"]]
            got = kol.compute_amounts(ctype, AMOUNT[c["amountType"]], c["amount"], c["tnc"] * 100, c["vat"] * 100)
            if c["type"] == "PERSON":
                pair = ((got["gross"], got["pit"], got["payable"]), (want["gross"], want["tax"], want["net"]))
            elif c["type"] == "COMPANY":
                pair = ((got["gross"], got["vat"], got["payable"]), (want["preVat"], want["vat"], want["total"]))
            else:
                pair = ((got["payable"],), (want["total"],))
            self.assertEqual(pair[0], tuple(float(x) for x in pair[1]), c)

    def test_ma_doi_tac(self):
        for c, want in zip(self.case["party"], self.js["party"]):
            self.assertEqual(T.party_code(TYPE[c["type"]], c["name"], c["manual"]), want, c)

    def test_ngan_hang_dia_chi_danh_xung(self):
        for c, want in zip(self.case["bank"], self.js["bank"]):
            self.assertEqual(T.bank_branch(*c), want)
        for c, want in zip(self.case["addr"], self.js["addr"]):
            self.assertEqual(T.address(c), want, c)
        for c, want in zip(self.case["honor"], self.js["honor"]):
            self.assertEqual(T.strip_honorific(c), want)

    def test_ngay_ky_va_ngay_bbnt(self):
        hol = {_d(h) for h in self.case["holidays"]}
        for c, before, after in zip(self.case["dates"], self.js["before"], self.js["after"]):
            b = T.business_day_before(_d(c["input"]), _d(c["boundary"]), hol, c["n"])
            a = T.business_day_after(_d(c["input"]), _d(c["boundary"]), hol, c["n"])
            self.assertEqual((str(b), str(a)), (before, after), c)


class NgayThucHien(unittest.TestCase):
    def test_cac_kieu_nhap(self):
        self.assertEqual(T.parse_service_dates("05,06/12", 2026), [dt.date(2026, 12, 5), dt.date(2026, 12, 6)])
        self.assertEqual(T.parse_service_dates("12/12/2026; 05/12", 2026), [dt.date(2026, 12, 5), dt.date(2026, 12, 12)])
        self.assertEqual(T.parse_service_dates("2026-12-05", 2025), [dt.date(2026, 12, 5)])
        self.assertEqual(T.parse_service_dates("5.1.27", 2026), [dt.date(2027, 1, 5)])
        self.assertEqual(T.parse_service_dates("", 2026), [])
        with self.assertRaises(ValueError):
            T.parse_service_dates("31/02", 2026)
        with self.assertRaises(ValueError):
            T.parse_service_dates("tuần sau", 2026)

    def test_so_hop_dong_theo_buoi_dau_va_quy_tac_mau(self):
        doc = {"air_dates": "21,22/07/2026", "contract_date": "2026-07-01", "request_type": kol.TEMPLATE_EC,
               "platform": "Shopee", "service_type": "Video", "payment_schedule": kol.PAY_ADVANCE}
        self.assertEqual(kol.service_dates(doc)[0], dt.date(2026, 7, 21))
        errs = kol.ec_template_errors(doc, "Cá nhân")
        self.assertTrue(any("Công ty - Livestream" in e for e in errs))
        self.assertTrue(any("cọc" in e for e in errs))
        self.assertEqual(kol.ec_template_errors(dict(doc, air_dates="x/y"), "Công ty")[-1][:18], "Không đọc được ngà")


if __name__ == "__main__":
    unittest.main()

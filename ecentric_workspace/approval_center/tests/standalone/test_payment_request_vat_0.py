# Copyright (c) 2026, eCentric and contributors
"""VAT 0% tren de nghi thanh toan (13/10/2026): lua chon rieng, gia tri "0.0" - khac
"Khong co VAT" ("0") ve chung tu nhung PnL tinh nhu nhau (CAST ra 0)."""
import json
import os
import re
import subprocess
import unittest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_HTML = os.path.join(_ROOT, "approval_center", "features", "payment_request", "ui", "main_section.html")
_FIX = os.path.join(_ROOT, "fixtures", "custom_field.json")


def _node(js):
    return subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30).stdout.strip()


class VatKhongPhanTram(unittest.TestCase):
    def setUp(self):
        self.html = open(_HTML, encoding="utf-8").read()

    def test_form_co_du_bon_lua_chon_dung_thu_tu(self):
        i = self.html.index('<select data-model="ec_vat_pct">')
        seg = self.html[i:self.html.index("</select>", i)]
        self.assertEqual(re.findall(r'<option value="([^"]+)"', seg), ["0", "0.0", "8", "10"])
        self.assertIn(">0%</option>", seg)
        self.assertIn(">Không có VAT</option>", seg)

    def test_fixture_khop_form(self):
        cf = [x for x in json.load(open(_FIX, encoding="utf-8"))
              if x["name"] == "EC Payment Request-ec_vat_pct"][0]
        self.assertEqual(cf["options"].split("\n"), ["0", "0.0", "8", "10"])
        self.assertEqual(cf["default"], "0")

    def test_trang_chi_tiet_hien_nhan_dung(self):
        i = self.html.index('kv("Thuế VAT",') + len('kv("Thuế VAT",')
        sau, j = 0, i
        while True:                      # lay bieu thuc doi so thu hai, can ngoac
            c = self.html[j]
            if c == "(":
                sau += 1
            elif c == ")":
                if sau == 0:
                    break
                sau -= 1
            j += 1
        expr = self.html[i:j]
        out = _node("var r=[];[null,'0','0.0','8','10'].forEach(function(v){var biz={ec_vat_pct:v};"
                    "r.push(" + expr + ")});console.log(JSON.stringify(r))")
        self.assertEqual(json.loads(out), ["Không có VAT", "Không có VAT", "0%", "8%", "10%"])


if __name__ == "__main__":
    unittest.main()

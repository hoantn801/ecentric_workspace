# Copyright (c) 2026, eCentric and contributors
"""Ngoai te ban quyen (27/11/2026): tra USD song song VND, ty gia go tay co goi y, chi phi thang luon VND;
nguoi quan ly tai san sua chi phi bat cu luc nao, moi lan sua co log xem duoc trong ngan chi tiet.

    python -m unittest ecentric_workspace.tai_san.tests.test_dot6
"""
import json
import os
import unittest

from ecentric_workspace.tai_san.tests.test_dot1 import APP, FIN, MGR
from ecentric_workspace.tai_san.tests.test_dot4 import LicenseCase
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import lifecycle as L


class TestMoney(LicenseCase):
    def test_money_rules(self):
        m = self.LS.money
        self.assertEqual(m("VND", vnd="9000000"), {"currency": "VND", "cost_fc": None, "exchange_rate": None,
                                                   "cost_per_cycle": 9000000.0})
        self.assertEqual(m("usd", "383.95", "26010")["cost_per_cycle"], round(383.95 * 26010))
        # so VND thuc tru tren sao ke giu nguyen, khong tinh lai
        self.assertEqual(m("USD", "383.95", "26010", "10050000")["cost_per_cycle"], 10050000.0)
        with self.assertRaises(L.TransitionError):
            m("USD", "383.95", "")                       # thieu ty gia
        with self.assertRaises(L.TransitionError):
            m("JPYX", "1", "1")                          # tien te chua ho tro
        with self.assertRaises(L.TransitionError):
            m("USD", "-1", "26000")

    def test_create_usd_and_monthly_in_vnd(self):
        r = self.LS.create(MGR, {"product": "PM2", "expiry_date": "2027-11-26", "billing_cycle": C.CY_YEARLY,
                                 "currency": "USD", "cost_fc": "383.95", "exchange_rate": "26000"})
        x = self.lr.lics[r["license"]]
        self.assertEqual((x.currency, x.cost_fc, x.exchange_rate, x.cost_per_cycle),
                         ("USD", 383.95, 26000.0, round(383.95 * 26000)))
        v = self.LV.licenses_view(MGR, {})
        row = [w for w in v["rows"] if w["name"] == r["license"]][0]
        self.assertEqual((row["currency"], row["cost_fc"]), ("USD", 383.95))
        self.assertAlmostEqual(row["monthly_cost"], round(383.95 * 26000) / 12, places=0)
        self.assertEqual(v["rates"]["USD"]["rate"], 26010.0)
        self.assertIn("USD", v["currencies"])

    def test_manager_edits_rate_logged_and_visible(self):
        self.LS.update(MGR, "BQ1", {"currency": "USD", "cost_fc": "100", "exchange_rate": "25000"})
        self.LS.update(MGR, "BQ1", {"currency": "USD", "cost_fc": "100", "exchange_rate": "26000"})
        x = self.lr.lics["BQ1"]
        self.assertEqual(x.cost_per_cycle, 2600000)
        self.assertIn("Tỷ giá: 25.000 → 26.000", self.lr.logs[-1][1])
        d = self.LV.license_detail(MGR, "BQ1")
        self.assertTrue(d["logs"] and "Tỷ giá" in d["logs"][0]["text"])
        # chi Finance / nguoi quan ly thay log; truong chi phi an voi nguoi khong xem duoc tien
        self.assertIn("cost_fc", d["license"])

    def test_renew_in_license_currency(self):
        self.lr.lics["BQ1"].update(currency="USD", cost_fc=100, exchange_rate=25000, cost_per_cycle=2500000,
                                   expiry_date="2026-12-31")
        self.LS.renew(MGR, "BQ1", "2027-12-31", cost_fc="120", exchange_rate="26000")
        x = self.lr.lics["BQ1"]
        self.assertEqual((x.currency, x.cost_fc, x.cost_per_cycle), ("USD", 120.0, 3120000))
        self.assertEqual((self.lr.ren[-1]["currency"], self.lr.ren[-1]["cost_fc"], self.lr.ren[-1]["cost"]),
                         ("USD", 120.0, 3120000))
        self.LS.renew(MGR, "BQ1", "2028-12-31")             # trong = giu chi phi cu
        self.assertEqual(self.lr.lics["BQ1"]["cost_fc"], 120.0)
        self.LS.update(FIN, "BQ1", {"currency": "VND", "cost_per_cycle": "3000000"})
        x = self.lr.lics["BQ1"]
        self.assertEqual((x.currency, x.cost_fc, x.exchange_rate), ("VND", None, None))


class TestWiringDot6(unittest.TestCase):
    def test_fields(self):
        for dt, keys in (("ec_software_license", ("currency", "cost_fc", "exchange_rate", "cost_per_cycle")),
                         ("ec_software_license_renewal", ("currency", "cost_fc", "exchange_rate", "cost"))):
            with open(os.path.join(APP, "tai_san", "doctype", dt, dt + ".json"), encoding="utf-8") as fh:
                d = json.load(fh)
            self.assertEqual(d["field_order"], [f["fieldname"] for f in d["fields"]])
            f = {x["fieldname"]: x for x in d["fields"]}
            for k in keys:
                self.assertIn(k, f, dt + "." + k)
            self.assertEqual(f["currency"]["options"], "Currency")
            self.assertEqual(f["cost_fc"]["options"], "currency")


if __name__ == "__main__":
    unittest.main()

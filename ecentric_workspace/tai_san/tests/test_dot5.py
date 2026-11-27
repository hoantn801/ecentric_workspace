# Copyright (c) 2026, eCentric and contributors
"""Danh muc (27/11/2026): phan mem cho ban quyen + mau thiet bi cho Nhap thiet bi - chan ten lech, gop.

    python -m unittest ecentric_workspace.tai_san.tests.test_dot5
"""
import json
import os
import unittest

from ecentric_workspace.tai_san.tests.test_dot1 import APP, FIN, MGR, STAFF, FakeRepo, Row, _install, _restore
from ecentric_workspace.tai_san.tests.test_dot4 import LicenseCase, lic
from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import catalog as CAT
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import lifecycle as L


class TestCatalog(unittest.TestCase):
    def test_name_key_folds_case_accents_spaces(self):
        self.assertEqual(CAT.name_key("Windows 11 Pro"), CAT.name_key(" windows  11-PRO "))
        self.assertEqual(CAT.name_key("Phần mềm Đồ hoạ"), "phanmemdohoa")

    def test_similar_catches_misspellings_not_unrelated(self):
        rows = [{"name": "PM1", "label": "Windows 11 Pro"}, {"name": "PM2", "label": "Adobe Photoshop"}]
        for typo in ("wins 11 pro", "window 11 pro", "Windows11 Pro"):
            self.assertEqual([r["name"] for r in CAT.similar(typo, rows, C.PRODUCT_SIMILAR_RATIO)], ["PM1"], typo)
        self.assertEqual(CAT.similar("Figma", rows, C.PRODUCT_SIMILAR_RATIO), [])

    def test_code_for_is_readable_and_unique(self):
        self.assertEqual(CAT.code_for("Dell Latitude 5420", "EC", set()), "EC-DELL-LATITUDE-5420")
        self.assertEqual(CAT.code_for("Dell Latitude 5420", "EC", {"EC-DELL-LATITUDE-5420"}),
                         "EC-DELL-LATITUDE-5420-2")


class TestProducts(LicenseCase):
    def setUp(self):
        super().setUp()
        from ecentric_workspace.tai_san import product_service
        self.PS = product_service

    def test_staff_cannot_add(self):
        with self.assertRaises(A.AccessDenied):
            self.PS.create_product(STAFF, {"product_name": "Figma"})

    def test_exact_duplicate_returns_existing(self):
        r = self.PS.create_product(MGR, {"product_name": "  microsoft-365 "})
        self.assertEqual(r["exact"]["name"], "PM1")
        self.assertEqual(len(self.lr.prods), 2)

    def test_similar_asks_then_force_creates_with_type_and_group(self):
        r = self.PS.create_product(MGR, {"product_name": "Adobe C.C Pro"})
        self.assertIn("similar", r)
        r = self.PS.create_product(MGR, {"product_name": "Figma", "vendor": "Figma", "category": "Thiết kế",
                                         "license_type": C.LT_SUBSCRIPTION, "billing_cycle": C.CY_MONTHLY})
        p = self.lr.prods[r["product"]]
        self.assertEqual((p.product_name, p.category, p.billing_cycle, p.name_key),
                         ("Figma", "Thiết kế", C.CY_MONTHLY, "figma"))
        with self.assertRaises(L.TransitionError):
            self.PS.create_product(MGR, {"product_name": "X1", "category": "Bừa"}, force=True)
        r = self.PS.create_product(MGR, {"product_name": "Office LTSC", "license_type": C.LT_PERPETUAL,
                                         "billing_cycle": C.CY_YEARLY}, force=True)
        self.assertIsNone(self.lr.prods[r["product"]].billing_cycle)      # vinh vien: khong co ky

    def test_rename_propagates_to_licenses(self):
        self.PS.update_product(MGR, "PM1", {"product_name": "Microsoft 365 Business", "category": "Văn phòng",
                                            "vendor": "Microsoft"})
        x = self.lr.lics["BQ1"]
        self.assertEqual((x.license_name, x.vendor), ("Microsoft 365 Business", "Microsoft"))
        with self.assertRaises(L.TransitionError):                         # doi ten trung phan mem khac
            self.PS.update_product(MGR, "PM1", {"product_name": "adobe cc"})

    def test_merge_moves_licenses_and_disables_source(self):
        self.lr.lics["BQ2"] = lic(name="BQ2", product="PM3", license_name="wins 11 pro")
        self.lr.prods["PM3"] = Row({"name": "PM3", "product_name": "wins 11 pro", "name_key": "wins11pro",
                                    "vendor": None, "category": "Khác", "disabled": 0, "note": None})
        self.lr.prods["PM4"] = Row({"name": "PM4", "product_name": "Windows 11 Pro", "name_key": "windows11pro",
                                    "vendor": "Microsoft", "category": "Văn phòng", "disabled": 0, "note": None})
        r = self.PS.merge_product(MGR, "PM3", "PM4")
        self.assertEqual(r["licenses"], 1)
        x = self.lr.lics["BQ2"]
        self.assertEqual((x.product, x.license_name, x.category), ("PM4", "Windows 11 Pro", "Văn phòng"))
        self.assertTrue(self.lr.prods["PM3"]["disabled"])
        with self.assertRaises(L.TransitionError):
            self.LS.create(MGR, {"product": "PM3", "license_type": C.LT_PERPETUAL})   # nguon da ngung
        with self.assertRaises(L.TransitionError):
            self.PS.merge_product(MGR, "PM4", "PM4")

    def test_link_unlinked_is_idempotent(self):
        self.lr.lics["BQ1"]["product"] = None
        self.lr.lics["BQ2"] = lic(name="BQ2", product=None, license_name="microsoft 365", vendor="MS")
        self.lr.lics["BQ3"] = lic(name="BQ3", product=None, license_name="Canva Pro", category="Thiết kế")
        r = self.PS.link_unlinked(MGR)
        self.assertEqual(r, {"created": 1, "linked": 3})
        self.assertEqual({self.lr.lics[n]["product"] for n in ("BQ1", "BQ2")}, {"PM1"})
        self.assertEqual(self.lr.prods["PM1"]["vendor"], "MS")              # dien hang con trong
        self.assertEqual(self.PS.link_unlinked(MGR), {"created": 0, "linked": 0})

    def test_change_license_product_and_views(self):
        self.LS.update(MGR, "BQ1", {"product": "PM2"})
        self.assertEqual(self.lr.lics["BQ1"]["license_name"], "Adobe CC")
        self.LS.create(MGR, {"product": "PM2", "expiry_date": "2027-11-26", "cost_per_cycle": 600_000})
        v = self.LV.licenses_view(MGR, {"product": "PM2"})
        self.assertEqual(len(v["rows"]), 2)
        g = v["groups"]
        self.assertEqual((len(g), g[0]["licenses"], g[0]["label"]), (1, 2, "Adobe CC"))
        p = self.LV.products_view(MGR)
        self.assertEqual({r["name"]: r["licenses"] for r in p["rows"]}, {"PM1": 0, "PM2": 2})


class TestModels(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepo([{"name": "A1", "asset_name": "Laptop cũ", "item_code": "LAPTOP", "item_name": "Laptop",
                               "asset_category": "LAPTOP", C.OPS_STATUS_FIELD: C.ST_AVAILABLE}],
                             categories={"LAPTOP": {"name": "LAPTOP"}, "MONITOR": {"name": "MONITOR"}})
        self.saved = _install(self.repo)
        from ecentric_workspace.tai_san import repository as R
        self.R = R
        self.items = {"LAPTOP": Row({"name": "LAPTOP", "item_name": "Laptop", "asset_category": "LAPTOP",
                                     "item_group": "Tài sản", "stock_uom": "Nos"})}
        self.extra = {}
        for n, f in (("fixed_asset_items", lambda: list(self.items.values())),
                     ("item_codes", lambda: set(self.items)), ("insert_item", self._insert)):
            self.extra[n] = getattr(R, n)
            setattr(R, n, f)
        from ecentric_workspace.tai_san import model_service, service, component_service
        self.MS, self.S, self.CS = model_service, service, component_service

    def tearDown(self):
        for n, f in self.extra.items():
            setattr(self.R, n, f)
        _restore(self.saved)

    def _insert(self, values):
        self.items[values["item_code"]] = Row(dict(values, name=values["item_code"]))
        return values["item_code"]

    def test_create_model_copies_group_and_blocks_duplicates(self):
        with self.assertRaises(A.AccessDenied):
            self.MS.create_model(STAFF, {"item_name": "Dell 5420", "asset_category": "LAPTOP"})
        with self.assertRaises(L.TransitionError):
            self.MS.create_model(MGR, {"item_name": "Dell 5420", "asset_category": "BUA"})
        r = self.MS.create_model(MGR, {"item_name": "Dell Latitude 5420", "asset_category": "LAPTOP"})
        it = self.items[r["item"]]
        self.assertEqual((it.name, it.item_group, it.stock_uom, it.is_fixed_asset, it.is_stock_item),
                         ("EC-DELL-LATITUDE-5420", "Tài sản", "Nos", 1, 0))
        self.assertEqual(self.MS.create_model(MGR, {"item_name": "dell latitude-5420", "asset_category": "LAPTOP"})
                         ["exact"]["name"], "EC-DELL-LATITUDE-5420")
        self.assertIn("similar", self.MS.create_model(MGR, {"item_name": "Dell Lattitude 5420",
                                                             "asset_category": "LAPTOP"}))

    def test_change_model_on_asset_moves_category(self):
        self._insert({"item_code": "EC-LG-27", "item_name": "LG 27UL500", "asset_category": "MONITOR",
                      "is_fixed_asset": 1})
        self.S.update_info(MGR, "A1", {"item_code": "EC-LG-27"})
        a = self.repo.assets["A1"]
        self.assertEqual((a.item_code, a.item_name, a.asset_category), ("EC-LG-27", "LG 27UL500", "MONITOR"))
        with self.assertRaises(L.TransitionError):
            self.S.update_info(MGR, "A1", {"item_code": "KHONG-CO"})
        self.S.update_info(FIN, "A1", {"item_code": "LAPTOP"})            # Finance khong doi mau
        self.assertEqual(self.repo.assets["A1"]["item_code"], "EC-LG-27")


class TestWiringDot5(unittest.TestCase):
    def test_doctype_patch_api(self):
        path = os.path.join(APP, "tai_san", "doctype", "ec_software_product", "ec_software_product.json")
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        self.assertEqual((d["name"], d["module"]), (C.PRODUCT_DT, C.MODULE))
        self.assertEqual(d["field_order"], [f["fieldname"] for f in d["fields"]])
        f = {x["fieldname"]: x for x in d["fields"]}
        self.assertEqual(f["category"]["options"].split("\n"), list(C.LICENSE_CATEGORIES))
        self.assertTrue(f["name_key"].get("unique") and f["product_name"].get("unique"))
        self.assertFalse([p for p in d["permissions"] if p["role"] != "System Manager"
                          and (p.get("write") or p.get("create"))])
        with open(os.path.join(APP, "tai_san", "doctype", "ec_software_license", "ec_software_license.json"),
                  encoding="utf-8") as fh:
            lf = {x["fieldname"]: x for x in json.load(fh)["fields"]}
        self.assertEqual(lf["product"]["options"], C.PRODUCT_DT)
        with open(os.path.join(APP, "patches.txt"), encoding="utf-8") as fh:
            self.assertIn("ecentric_workspace.tai_san.patches.p004_danh_muc", fh.read().split("\n"))
        with open(os.path.join(APP, "tai_san", "controllers", "api.py"), encoding="utf-8") as fh:
            api = fh.read()
        for fn in ("def products(", "def create_product(", "def update_product(", "def merge_product(",
                   "def create_model("):
            self.assertIn(fn, api)


if __name__ == "__main__":
    unittest.main()

# Copyright (c) 2026, eCentric and contributors
"""Quan ly tai san dot 0 - quy tac thuan + dong bo fixtures / hooks / patches (khong can bench).

    python -m unittest ecentric_workspace.tai_san.tests.test_tai_san
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
APP = os.path.join(ROOT, "ecentric_workspace")
sys.path.insert(0, ROOT)

from ecentric_workspace.tai_san import constants as C  # noqa: E402
from ecentric_workspace.tai_san import domain as D  # noqa: E402

SITE_OPTIONS = "Available\nIn Use\nReserved\nUnder Repair\nLost\nDisposed\nRetired"


def asset(name, **kw):
    row = {"name": name, C.TAG_FIELD: "EC2024%05d" % int(name[-3:]), C.SERIAL_FIELD: "SN" + name,
           C.OPS_STATUS_FIELD: C.ST_IN_USE, "custodian": "EMP-" + name, "asset_category": "LAPTOP",
           "purchase_date": "2025-08-01", "available_for_use_date": "2025-08-01",
           "net_purchase_amount": 10_000_000, C.INSTALLED_ON_FIELD: None}
    row.update(kw)
    return row


class TestStatusOptions(unittest.TestCase):
    def test_adds_new_states_in_canonical_order(self):
        out = D.merge_status_options(SITE_OPTIONS).split("\n")
        self.assertEqual(out, list(C.STATUSES))
        self.assertIn(C.ST_PENDING_CHECK, out)
        self.assertIn(C.ST_BROKEN, out)

    def test_never_drops_an_existing_value(self):
        out = D.merge_status_options(SITE_OPTIONS + "\nOn Loan").split("\n")
        self.assertEqual(out[-1], "On Loan")
        for v in SITE_OPTIONS.split("\n"):
            self.assertIn(v, out)

    def test_idempotent(self):
        once = D.merge_status_options(SITE_OPTIONS)
        self.assertEqual(D.merge_status_options(once), once)

    def test_empty(self):
        self.assertEqual(D.merge_status_options(None).split("\n"), list(C.STATUSES))

    def test_every_state_has_a_label(self):
        self.assertEqual(set(C.STATUS_LABELS), set(C.STATUSES))


class TestCategoryDefaults(unittest.TestCase):
    def test_site_categories(self):
        # 5 Asset Category dang co tren site 26/11/2026
        for cat in ("LAPTOP", "RAM", "PRINTER", "MONITOR", "PC"):
            self.assertIsNotNone(D.category_defaults(cat), cat)

    def test_component_and_life(self):
        self.assertEqual(D.category_defaults("ram")[:2], (24, 1))
        self.assertEqual(D.category_defaults("Laptop")[:2], (36, 0))

    def test_unknown(self):
        self.assertIsNone(D.category_defaults("CAMERA"))

    def test_life_under_fixed_asset_cap(self):
        for row in C.CATEGORY_DEFAULTS.values():
            self.assertLessEqual(row["life"], C.MAX_LIFE_UNDER_THRESHOLD)


class TestAudit(unittest.TestCase):
    def test_clean_asset_has_no_issue(self):
        self.assertEqual(D.audit_assets([asset("A001")], {"EMP-A001": "Active"}), {})

    def test_holder_left_still_in_use(self):
        out = D.audit_assets([asset("A001")], {"EMP-A001": "Left"})
        self.assertEqual(out["A001"], [C.ISSUE_HOLDER_LEFT])

    def test_available_with_holder(self):
        out = D.audit_assets([asset("A001", **{C.OPS_STATUS_FIELD: C.ST_AVAILABLE})])
        self.assertIn(C.ISSUE_AVAILABLE_WITH_HOLDER, out["A001"])

    def test_in_use_without_holder_but_printer_is_shared(self):
        out = D.audit_assets([asset("A001", custodian=None),
                              asset("A002", custodian=None, asset_category="PRINTER")])
        self.assertEqual(out["A001"], [C.ISSUE_IN_USE_NO_HOLDER])
        self.assertNotIn("A002", out)

    def test_duplicate_serial_ignores_spaces_and_case(self):
        out = D.audit_assets([asset("A001", **{C.SERIAL_FIELD: "G5DHR14"}),
                              asset("A002", **{C.SERIAL_FIELD: " g5dhr14"})])
        self.assertEqual(out["A001"], [C.ISSUE_DUP_SERIAL])
        self.assertEqual(out["A002"], [C.ISSUE_DUP_SERIAL])

    def test_placeholder_serial_is_missing_not_duplicate(self):
        out = D.audit_assets([asset("A001", **{C.SERIAL_FIELD: "UNKNOW"}),
                              asset("A002", **{C.SERIAL_FIELD: "UNKNOW"})])
        self.assertEqual(out["A001"], [C.ISSUE_NO_SERIAL])
        self.assertEqual(out["A002"], [C.ISSUE_NO_SERIAL])

    def test_bad_tag(self):
        out = D.audit_assets([asset("A001", **{C.TAG_FIELD: "ec202400046"}),
                              asset("A002", **{C.TAG_FIELD: "EC202400006-1"})])
        self.assertEqual(out["A001"], [C.ISSUE_BAD_TAG])
        self.assertNotIn("A002", out)

    def test_use_before_purchase(self):
        out = D.audit_assets([asset("A001", purchase_date="2026-09-01",
                                    available_for_use_date="2026-01-01")])
        self.assertEqual(out["A001"], [C.ISSUE_DATE_ORDER])

    def test_component_price_and_parent_status(self):
        mother = asset("A001", **{C.OPS_STATUS_FIELD: C.ST_AVAILABLE}, custodian=None)
        ram = asset("A002", asset_category="RAM", custodian=None, net_purchase_amount=10_000_000,
                    **{C.INSTALLED_ON_FIELD: "A001", C.OPS_STATUS_FIELD: C.ST_UNDER_REPAIR})
        out = D.audit_assets([mother, ram])
        self.assertEqual(out["A002"], [C.ISSUE_COMPONENT_PRICE, C.ISSUE_COMPONENT_STATUS])
        self.assertNotIn("A001", out)

    def test_missing_price(self):
        out = D.audit_assets([asset("A001", net_purchase_amount=0)])
        self.assertEqual(out["A001"], [C.ISSUE_NO_PRICE])

    def test_every_issue_has_a_label(self):
        codes = {v for k, v in vars(C).items() if k.startswith("ISSUE_") and isinstance(v, str)}
        self.assertEqual(codes, set(C.ISSUE_LABELS))


class TestWiring(unittest.TestCase):
    """Fixtures / hooks / patches / modules khop nhau - thieu mot cho la rebuild site mat field."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(APP, "fixtures", "custom_field.json"), encoding="utf-8") as fh:
            cls.fields = [r for r in json.load(fh) if r.get("module") == C.MODULE]
        with open(os.path.join(APP, "hooks.py"), encoding="utf-8") as fh:
            cls.hooks = fh.read()

    def test_fixture_fields_listed_in_hooks(self):
        self.assertTrue(self.fields)
        for row in self.fields:
            self.assertIn('"%s"' % row["name"], self.hooks, row["name"])

    def test_fixture_fields_only_on_native_doctypes_and_ec_prefixed(self):
        for row in self.fields:
            self.assertIn(row["dt"], (C.ASSET, C.CATEGORY))
            self.assertTrue(row["fieldname"].startswith("ec_"), row["fieldname"])
            self.assertEqual(row["name"], "%s-%s" % (row["dt"], row["fieldname"]))

    def test_insert_after_chain_resolves(self):
        by_dt = {}
        for row in self.fields:
            by_dt.setdefault(row["dt"], set()).add(row["fieldname"])
        roots = {C.ASSET: "custom_installed_date", C.CATEGORY: "asset_category_name"}
        for row in self.fields:
            ok = row["insert_after"] in by_dt[row["dt"]] or row["insert_after"] == roots[row["dt"]]
            self.assertTrue(ok, row["name"])

    def test_select_options_match_constants(self):
        opts = {r["fieldname"]: r.get("options") for r in self.fields}
        self.assertEqual(opts["ec_condition"].split("\n"), list(C.CONDITIONS))
        self.assertEqual(opts["ec_ownership"].split("\n"), list(C.OWNERSHIPS))
        self.assertEqual(opts["ec_spec"], C.SPEC_DT)

    def test_spec_doctype(self):
        path = os.path.join(APP, "tai_san", "doctype", "ec_asset_spec", "ec_asset_spec.json")
        with open(path, encoding="utf-8") as fh:
            dt = json.load(fh)
        self.assertEqual((dt["name"], dt["module"], dt["istable"]), (C.SPEC_DT, C.MODULE, 1))
        self.assertEqual(dt["field_order"], [f["fieldname"] for f in dt["fields"]])

    def test_patch_and_module_registered(self):
        with open(os.path.join(APP, "patches.txt"), encoding="utf-8") as fh:
            patches = fh.read().split("\n")
        self.assertIn("ecentric_workspace.tai_san.patches.p001_setup", patches)
        with open(os.path.join(APP, "modules.txt"), encoding="utf-8") as fh:
            self.assertIn(C.MODULE, fh.read().split("\n"))
        folder = re.sub(r"\s+", "_", C.MODULE.lower())
        self.assertTrue(os.path.isdir(os.path.join(APP, folder)))


if __name__ == "__main__":
    unittest.main()

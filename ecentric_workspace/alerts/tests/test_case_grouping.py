"""Case-grouping fix tests (2026-06-11).

Bug: Case grouped by brand+sku+rule only -> Lazada P02056 occurrences
attached to open Shopee case EC-AL-000708. Fix: brand+platform+shop+sku+rule.

Part 1 (pure, runs anywhere): dedupe_keys.case_key / occurrence_key.
Part 2 (source-text, runs anywhere): alert_engine wiring + api_repair safety.
Part 3 (bench-only, auto-skipped without a site): full engine behavior.

    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_case_grouping
"""
import os
import unittest

from ecentric_workspace.alerts.services import dedupe_keys as dk


def _src(rel):
    path = os.path.join(os.path.dirname(__file__), "..", rel)
    with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestCaseKey(unittest.TestCase):
    def test_includes_platform_and_shop(self):
        k = dk.case_key("FES-VN", "Lazada", "FES-VN-LAZADA", "P02056",
                        "below_min", "ODVN26061079FEA963", "1:P02056")
        self.assertEqual(k, "case|FES-VN|Lazada|FES-VN-LAZADA|P02056|"
                            "below_min|ODVN26061079FEA963|1:P02056")

    def test_requirement_separate_cases_per_platform_shop(self):
        """REQ 6a: same brand+SKU+rule, different platform/shop -> DIFFERENT
        case identity (the exact EC-AL-000708 scenario)."""
        shopee = dk.case_key("FES-VN", "Shopee", "FES-VN-SHOPEE", "P02056",
                             "below_min", "O1", "L1")
        lazada = dk.case_key("FES-VN", "Lazada", "FES-VN-LAZADA", "P02056",
                             "below_min", "O1", "L1")
        self.assertNotEqual(shopee, lazada)
        # shop alone differs -> still separate
        self.assertNotEqual(
            dk.case_key("FES-VN", "Lazada", "SHOP-A", "P02056", "below_min", "O1", "L1"),
            dk.case_key("FES-VN", "Lazada", "SHOP-B", "P02056", "below_min", "O1", "L1"))

    def test_requirement_same_scope_same_identity(self):
        """REQ 6b precondition: two Lazada orders share the SAME case scope -
        the open-case lookup (not the key) reuses the case; the key only
        differs by first order/line, which is irrelevant once a case is open."""
        a = dk.case_key("FES-VN", "Lazada", "FES-VN-LAZADA", "P02056",
                        "below_min", "O1", "L1")
        b = dk.case_key("FES-VN", "Lazada", "FES-VN-LAZADA", "P02056",
                        "below_min", "O2", "L1")
        self.assertEqual(a.rsplit("|", 2)[0], b.rsplit("|", 2)[0])  # same scope prefix

    def test_requirement_repull_occurrence_identity_stable(self):
        """REQ 6c: occurrence key is per order+line+rule - identical on
        re-pull (engine no-ops on existing dedupe_key), new order = new key."""
        k1 = dk.occurrence_key("ODVN26061079FEA963", "1:P02056", "below_min")
        self.assertEqual(k1, dk.occurrence_key("ODVN26061079FEA963", "1:P02056", "below_min"))
        self.assertNotEqual(k1, dk.occurrence_key("ODVN260610A8C002C0", "1:P02056", "below_min"))

    def test_fit_140(self):
        k = dk.case_key("B" * 60, "P" * 30, "S" * 60, "K" * 40, "below_min", "O", "L")
        self.assertLessEqual(len(k), 140)
        self.assertIn("#", k)

    def test_none_safe(self):
        k = dk.case_key("FES-VN", None, None, "P02056", "below_min", "O1", "L1")
        self.assertEqual(k, "case|FES-VN|||P02056|below_min|O1|L1")


class TestEngineWiring(unittest.TestCase):
    @property
    def src(self):
        return _src("services/alert_engine.py")

    def test_lookup_scoped_by_platform_shop(self):
        s = self.src
        self.assertIn('"platform": log.platform, "shop": log.shop,', s)
        # the lookup block contains all five scope fields
        block = s.split("def _find_or_create_case")[1].split("\ndef ")[0]
        for needle in ('"brand": log.brand', '"platform": log.platform',
                       '"shop": log.shop', '"seller_sku": line.seller_sku',
                       '"rule_code": rule_code'):
            self.assertIn(needle, block)

    def test_key_built_by_dedupe_keys_case_key(self):
        self.assertIn("dedupe_keys.case_key(", self.src)
        self.assertNotIn('_fit("case|%s|%s|%s|%s|%s"', self.src)  # old inline key gone

    def test_occurrence_dedupe_unchanged(self):
        """REQ 6c: re-pull no-dup path intact - existing occurrence short-
        circuits BEFORE any case create/bump."""
        body = self.src.split("def _record_price_violation")[1].split("\ndef ")[0]
        self.assertIn("dedupe_keys.occurrence_key(", body)
        self.assertLess(body.find("if existing:"),
                        body.find("_find_or_create_case("))
        self.assertIn("return existing.name, False, existing.case", body)

    def test_bump_case_intact(self):
        body = self.src.split("def _bump_case")[1]
        for needle in ("occurrence_count", "first_seen_at", "last_seen_at",
                       "worst_gap_percent"):
            self.assertIn(needle, body)


class TestRepairSafety(unittest.TestCase):
    @property
    def src(self):
        return _src("api_repair.py")

    def test_sm_only_and_dry_run_default(self):
        s = self.src
        self.assertIn('frappe.only_for("System Manager")', s)
        self.assertIn("def repair_case_grouping(brand=None, dry_run=1):", s)
        self.assertIn("if dry:", s)

    def test_no_deletes_no_status_change(self):
        s = self.src
        self.assertNotIn(".delete(", s)
        self.assertNotIn("frappe.delete_doc", s)
        self.assertNotIn('case.status =', s)
        self.assertNotIn('"status", ', s.split("def repair_case_grouping")[1])

    def test_recalc_covers_required_rollups(self):
        body = self.src.split("def _recalc")[1].split("\ndef ")[0]
        for f in ("occurrence_count", "first_seen_at", "last_seen_at",
                  "worst_gap_percent", "effective_check_price"):
            self.assertIn(f, body)

    def test_scope_price_rules_only(self):
        self.assertIn('PRICE_RULES = ("below_min", "above_high", '
                      '"severe_price_drop",', self.src)
        self.assertNotIn("missing_policy", self.src.split("PRICE_RULES")[1]
                         .split(")")[0])


def _bench():
    try:
        import frappe
        return bool(getattr(frappe, "db", None)) and frappe.db is not None
    except Exception:
        return False


@unittest.skipUnless(_bench(), "bench site required")
class TestEngineOnBench(unittest.TestCase):
    """REQ 6 full-behavior tests - run via bench run-tests on a dev site with
    [PM TEST]-style fixtures. Kept minimal: exercises _find_or_create_case
    directly with two fake logs differing only in platform/shop."""

    def _mk(self, platform, shop, order, line_id="1:SKU-TEST"):
        import frappe
        log = frappe._dict(brand="FES-VN", platform=platform, shop=shop,
                           external_order_id=order, order_datetime=None,
                           order_status="300", source_system="Omisell",
                           name="TEST-LOG-%s" % order)
        line = frappe._dict(seller_sku="SKU-CASEGRP-TEST", item=None,
                            product_name="t", external_line_id=line_id)
        return log, line

    def test_separate_cases_then_same_case_bump(self):
        import frappe
        from ecentric_workspace.alerts.services import alert_engine as eng
        hit = {"severity": "Critical", "gap_percent": 10.0,
               "recommended_action": "Notify Only"}
        ev = {"price_components_used": "test", "rsp_price": 100.0}
        log1, line1 = self._mk("Shopee", "T-SHOPEE", "T-O1")
        log2, line2 = self._mk("Lazada", "T-LAZADA", "T-O2")
        c1, created1 = eng._find_or_create_case(log1, line1, "below_min", hit,
                                                90.0, ev, None, 100.0, None, "L5")
        c2, created2 = eng._find_or_create_case(log2, line2, "below_min", hit,
                                                90.0, ev, None, 100.0, None, "L5")
        try:
            self.assertNotEqual(c1, c2)            # REQ 6a
            c2b, created2b = eng._find_or_create_case(
                log2, line2, "below_min", hit, 90.0, ev, None, 100.0, None, "L5")
            self.assertEqual(c2, c2b)              # REQ 6b: same scope reuses
            self.assertFalse(created2b)
        finally:
            for occf in frappe.get_all("EC Alert Occurrence",
                                       filters={"case": ["in", [c1, c2]]}):
                frappe.delete_doc("EC Alert Occurrence", occf.name, force=1)
            for nm in {c1, c2}:
                frappe.delete_doc("EC Alert", nm, force=1)


if __name__ == "__main__":
    unittest.main()

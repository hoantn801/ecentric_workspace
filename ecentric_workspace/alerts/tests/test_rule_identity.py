"""RC5-4 regression: api_rules.save_rule must FIND-OR-UPDATE an existing EC Alert
Rule by scope identity (brand + rule_code + platform + shop + seller_sku + item) so
a create-without-name never produces a DUPLICATE row, and re-adding a customization
that was removed (Paused) resumes that same row instead of spawning a second one.

Pure test: stubs `frappe` + the permissions module so `api_rules` imports without a
Frappe site, then drives the real `_find_rule_by_identity` against canned rows.

    bench run-tests --module ecentric_workspace.alerts.tests.test_rule_identity
    # or, frappe-free:  python -m unittest ecentric_workspace.alerts.tests.test_rule_identity
"""
import sys
import types
import unittest


def _install_stubs():
    if "frappe" not in sys.modules:
        fr = types.ModuleType("frappe")
        fr.whitelist = lambda *a, **k: (lambda f: f)
        fr._ = lambda s: s
        def _throw(*a, **k):
            raise Exception(a[0] if a else "throw")
        fr.throw = _throw
        fr.session = types.SimpleNamespace(user="tester@example.com")
        fr.PermissionError = type("PermissionError", (Exception,), {})
        fr.get_all = lambda *a, **k: []           # overridden per-test
        fr.get_doc = lambda *a, **k: None
        fr.new_doc = lambda *a, **k: None
        sys.modules["frappe"] = fr
        utils = types.ModuleType("frappe.utils")
        utils.now_datetime = lambda: None
        sys.modules["frappe.utils"] = utils
    # stub the permissions module api_rules imports at module load.
    perms = types.ModuleType("ecentric_workspace.alerts.permissions")
    perms.require_alert_center_access = lambda *a, **k: None
    perms.can_manage_policy = lambda *a, **k: True
    perms.can_activate_rule = lambda *a, **k: False
    perms.require_brand_access = lambda *a, **k: None
    perms.ALL_BRANDS = object()
    sys.modules["ecentric_workspace.alerts.permissions"] = perms


_install_stubs()
from ecentric_workspace.alerts import api_rules  # noqa: E402


def _rows(*recs):
    """Build the get_all return shape (objects with attribute access)."""
    return [types.SimpleNamespace(**r) for r in recs]


class TestFindRuleByIdentity(unittest.TestCase):
    """The dedup decision: which existing row (if any) a create maps onto."""

    def _patch_getall(self, rows):
        api_rules.frappe.get_all = lambda *a, **k: rows

    def test_matches_platform_override_ignoring_empty_scope(self):
        # one Shopee platform override exists (no shop/sku/item) -> identity match.
        self._patch_getall(_rows(
            {"name": "EC-AR-1", "shop": None, "seller_sku": "", "item": None}))
        got = api_rules._find_rule_by_identity(
            {"brand": "B", "rule_code": "below_min", "platform": "Shopee"})
        self.assertEqual(got, "EC-AR-1")

    def test_does_not_match_a_shop_or_sku_exception_sharing_platform(self):
        # a Shop/SKU exception on the same platform is NOT the platform override.
        self._patch_getall(_rows(
            {"name": "EC-AR-9", "shop": "ShopA", "seller_sku": None, "item": None},
            {"name": "EC-AR-10", "shop": None, "seller_sku": "SKU1", "item": None}))
        got = api_rules._find_rule_by_identity(
            {"brand": "B", "rule_code": "below_min", "platform": "Shopee"})
        self.assertIsNone(got)

    def test_matches_even_when_existing_is_paused(self):
        # get_all returns the paused row (status not part of the filter) -> the
        # create maps onto it instead of duplicating. (status isn't in the projected
        # fields here; identity is scope-only, which is the point.)
        self._patch_getall(_rows(
            {"name": "EC-AR-7", "shop": None, "seller_sku": None, "item": None}))
        got = api_rules._find_rule_by_identity(
            {"brand": "B", "rule_code": "severe_price_drop", "platform": "Lazada"})
        self.assertEqual(got, "EC-AR-7")

    def test_brand_default_identity_uses_all(self):
        self._patch_getall(_rows(
            {"name": "EC-AR-3", "shop": None, "seller_sku": None, "item": None}))
        got = api_rules._find_rule_by_identity(
            {"brand": "B", "rule_code": "above_high", "platform": "All"})
        self.assertEqual(got, "EC-AR-3")

    def test_none_when_no_candidate(self):
        self._patch_getall([])
        self.assertIsNone(api_rules._find_rule_by_identity(
            {"brand": "B", "rule_code": "below_min", "platform": "Shopee"}))

    def test_none_without_brand_or_rule_code(self):
        self._patch_getall(_rows({"name": "X", "shop": None, "seller_sku": None,
                                  "item": None}))
        self.assertIsNone(api_rules._find_rule_by_identity({"platform": "Shopee"}))


class TestNorm(unittest.TestCase):
    def test_norm_treats_none_and_empty_equal(self):
        self.assertEqual(api_rules._norm(None), api_rules._norm(""))
        self.assertEqual(api_rules._norm("Shopee"), "Shopee")


if __name__ == "__main__":
    unittest.main()

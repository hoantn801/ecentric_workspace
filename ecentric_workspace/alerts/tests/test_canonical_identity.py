"""RC6 regression: CANONICAL Price Setup identity = brand + platform + normalized
seller_sku. Shop AND the legacy ERP `item` are NOT part of the identity. At most one
non-cancelled (Draft/Active/Paused) policy per canonical identity; empty SKU is the
single brand/platform fallback; Expired/Inactive are the retired ("cancelled")
statuses and do not participate (so an operator can always retire a duplicate).

Pure test: stubs `frappe.get_all` so policy_scope's canonical logic runs frappe-free.

    bench run-tests --module ecentric_workspace.alerts.tests.test_canonical_identity
    # or:  python -m unittest ecentric_workspace.alerts.tests.test_canonical_identity
"""
import sys
import types
import unittest

if "frappe" not in sys.modules:
    _fr = types.ModuleType("frappe")
    _fr.get_all = lambda *a, **k: []
    sys.modules["frappe"] = _fr

from ecentric_workspace.alerts.services import policy_scope as ps  # noqa: E402


def _rows(*recs):
    return [types.SimpleNamespace(**r) for r in recs]


def _row(name, status="Active", platform="TikTok", shop="", seller_sku="P02056",
         item=None, brand="FES-VN", modified="2026-06-16"):
    return dict(name=name, status=status, platform=platform, shop=shop,
                seller_sku=seller_sku, item=item, brand=brand, modified=modified)


def _live_stub(all_rows):
    """get_all stub that honours the status-in-LIVE filter the code passes."""
    def ga(*a, **k):
        st = (k.get("filters") or {}).get("status")
        rows = all_rows
        if isinstance(st, list) and st[0] == "in":
            rows = [r for r in rows if r.status in st[1]]
        return rows
    return ga


class TestCanonicalKey(unittest.TestCase):
    def test_shop_ignored_and_sku_normalized(self):
        a = ps.canonical_key("FES-VN", "TikTok", "p02056 ")
        b = ps.canonical_key("FES-VN", "TikTok", " P02056")
        self.assertEqual(a, b)
        self.assertEqual(a, ("FES-VN", "TikTok", "P02056"))

    def test_empty_sku_is_single_fallback(self):
        # different/empty Item must NOT split the fallback identity (Item is ignored).
        self.assertEqual(ps.canonical_key("B", "TikTok", ""),
                         ps.canonical_key("B", "TikTok", None))
        self.assertEqual(ps.canonical_key("B", "TikTok", ""), ("B", "TikTok", ""))

    def test_sku_specific_distinct_from_fallback(self):
        self.assertNotEqual(ps.canonical_key("B", "TikTok", "P1"),
                            ps.canonical_key("B", "TikTok", ""))

    def test_canonical_key_takes_no_item(self):
        # signature must be (brand, platform, seller_sku) only.
        import inspect
        params = list(inspect.signature(ps.canonical_key).parameters)
        self.assertEqual(params, ["brand", "platform", "seller_sku"])


class TestFindCanonicalConflict(unittest.TestCase):
    def _set(self, rows):
        ps.frappe.get_all = _live_stub(rows)

    def test_same_bps_different_shop_conflicts(self):
        self._set(_rows(_row("EC-PP-1", shop="FES-VN-TIKTOK")))
        hit = ps.find_canonical_conflict("FES-VN", "TikTok", "P02056", exclude_name="NEW")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["name"], "EC-PP-1")

    def test_same_bps_one_shop_empty_conflicts(self):
        self._set(_rows(_row("EC-PP-1", shop="")))
        self.assertIsNotNone(
            ps.find_canonical_conflict("FES-VN", "TikTok", "P02056", exclude_name="NEW"))

    # --- RC6 correction 1: ERP Item must NOT split the fallback identity ----------
    def test_empty_sku_different_item_conflicts(self):
        self._set(_rows(_row("EC-PP-1", seller_sku="", item="IT-A")))
        self.assertIsNotNone(
            ps.find_canonical_conflict("FES-VN", "TikTok", "", exclude_name="NEW"),
            "two empty-SKU fallbacks (even with different Item) must conflict")

    def test_empty_sku_one_item_empty_one_populated_conflicts(self):
        self._set(_rows(_row("EC-PP-1", seller_sku="", item=None)))
        self.assertIsNotNone(
            ps.find_canonical_conflict("FES-VN", "TikTok", "", exclude_name="NEW"))
        self._set(_rows(_row("EC-PP-1", seller_sku="", item="IT-X")))
        self.assertIsNotNone(
            ps.find_canonical_conflict("FES-VN", "TikTok", "", exclude_name="NEW"))

    def test_fallback_vs_sku_specific_allowed(self):
        self._set(_rows(_row("EC-PP-1", seller_sku="")))
        self.assertIsNone(
            ps.find_canonical_conflict("FES-VN", "TikTok", "P02056", exclude_name="NEW"))
        self._set(_rows(_row("EC-PP-1", seller_sku="P02056")))
        self.assertIsNone(
            ps.find_canonical_conflict("FES-VN", "TikTok", "", exclude_name="NEW"))

    def test_different_non_empty_skus_allowed(self):
        self._set(_rows(_row("EC-PP-1", seller_sku="P99999")))
        self.assertIsNone(
            ps.find_canonical_conflict("FES-VN", "TikTok", "P02056", exclude_name="NEW"))

    def test_self_edit_does_not_conflict(self):
        self._set(_rows(_row("EC-PP-1")))
        self.assertIsNone(
            ps.find_canonical_conflict("FES-VN", "TikTok", "P02056", exclude_name="EC-PP-1"))


class TestRetireGuard(unittest.TestCase):
    """RC6 correction 2: the guard enforces uniqueness ONLY for a LIVE target status,
    so an operator can retire one of two existing duplicates."""

    def _set(self, rows):
        ps.frappe.get_all = _live_stub(rows)

    def setUp(self):
        # two legacy duplicate ACTIVE policies of the same canonical identity exist.
        self._set(_rows(_row("EC-PP-1"), _row("EC-PP-2")))

    def test_retire_one_to_inactive_succeeds(self):
        # saving EC-PP-1 with target status Inactive must be ALLOWED (guard skips).
        self.assertIsNone(ps.canonical_guard_conflict(
            "Inactive", "FES-VN", "TikTok", "P02056", exclude_name="EC-PP-1"))

    def test_retire_one_to_expired_succeeds(self):
        self.assertIsNone(ps.canonical_guard_conflict(
            "Expired", "FES-VN", "TikTok", "P02056", exclude_name="EC-PP-1"))

    def test_editing_surviving_live_row_allowed(self):
        # after EC-PP-2 is retired, only EC-PP-1 is live; editing it stays allowed.
        self._set(_rows(_row("EC-PP-1")))
        self.assertIsNone(ps.canonical_guard_conflict(
            "Active", "FES-VN", "TikTok", "P02056", exclude_name="EC-PP-1"))

    def test_creating_or_activating_another_duplicate_blocked(self):
        # a NEW/other row going Live while EC-PP-1 is live is still blocked.
        self._set(_rows(_row("EC-PP-1")))
        for st in ("Draft", "Active", "Paused"):
            hit = ps.canonical_guard_conflict(
                st, "FES-VN", "TikTok", "P02056", exclude_name="NEW")
            self.assertIsNotNone(hit, "a %s duplicate must be blocked" % st)
            self.assertEqual(hit["name"], "EC-PP-1")

    def test_self_edit_exclusion_still_correct(self):
        # EC-PP-1 editing itself (Active) does not self-conflict.
        self._set(_rows(_row("EC-PP-1")))
        self.assertIsNone(ps.canonical_guard_conflict(
            "Active", "FES-VN", "TikTok", "P02056", exclude_name="EC-PP-1"))

    def test_live_statuses_contract(self):
        self.assertEqual(ps.LIVE_STATUSES, ("Draft", "Active", "Paused"))


class TestDuplicateDiagnostic(unittest.TestCase):
    def test_groups_only_canonical_duplicates(self):
        ps.frappe.get_all = _live_stub(_rows(
            _row("EC-PP-1", shop="", item="IT-A"),
            _row("EC-PP-2", shop="FES-VN-TIKTOK", item="IT-B"),
            _row("EC-PP-3", seller_sku="OTHER")))
        groups = ps.canonical_duplicate_groups(["FES-VN"])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["count"], 2)
        self.assertEqual({m.name for m in groups[0]["members"]}, {"EC-PP-1", "EC-PP-2"})

    def test_empty_brand_scope_returns_empty_no_scan(self):
        # RC6 correction 3 backing: a caller with NO accessible brands ([]) must get
        # [] and NEVER trigger a full-table scan (cross-brand leak guard).
        called = {"n": 0}
        def ga(*a, **k):
            called["n"] += 1
            return []
        ps.frappe.get_all = ga
        self.assertEqual(ps.canonical_duplicate_groups([]), [])
        self.assertEqual(called["n"], 0, "must not query when brand scope is empty")


if __name__ == "__main__":
    unittest.main()

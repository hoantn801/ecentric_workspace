"""Step 6 (Price Setup lifecycle) + scope-conflict tests (2026-06-14).

Drives the REAL services.policy_scope + services.policy_setup with a stubbed
frappe + fake EC Alert / EC Price Policy stores and a scripted policy_lookup, so
the lifecycle bindings are deterministic (no DB). Mirrors the in-/tmp harness
used during development.

    bench run-tests --module ecentric_workspace.alerts.tests.test_policy_setup
"""
import sys
import types
import unittest


def _install_fake_frappe():
    if "frappe" in sys.modules and getattr(sys.modules["frappe"], "_ec_real", False):
        return  # real frappe (bench): the @skip guard below handles it
    f = types.ModuleType("frappe")
    f.session = types.SimpleNamespace(user="tester")
    f.flags = types.SimpleNamespace()
    f._ALERTS = {}
    f._POLICIES = []
    f._LOG = []

    def get_all(dt, filters=None, fields=None, **k):
        filters = filters or {}
        out = []
        if dt == "EC Price Policy":
            for p in f._POLICIES:
                if all(k2 in ("shop",) or p.get(k2) == v2 for k2, v2 in filters.items()):
                    out.append(types.SimpleNamespace(**p))
        elif dt == "EC Alert":
            for nm, a in f._ALERTS.items():
                ok = True
                for k2, v2 in filters.items():
                    if k2 == "status" and isinstance(v2, list) and v2 and v2[0] == "in":
                        if a.get("status") not in v2[1]:
                            ok = False
                    elif a.get(k2) != v2:
                        ok = False
                if ok:
                    row = {fn: a.get(fn) for fn in (fields or list(a.keys()))}
                    row["name"] = nm
                    out.append(types.SimpleNamespace(**row))
        return out

    class _AlertDoc:
        def __init__(self, nm):
            self._n = nm
            self.__dict__.update(f._ALERTS[nm])
            self.name = nm
        def get(self, k):
            return getattr(self, k, None)
        def save(self, ignore_permissions=False):
            import ecentric_workspace.alerts.services.case_lifecycle as cl
            if cl.is_terminal(self.status):
                if not getattr(self, "resolved_at", None):
                    self.resolved_at = "now"
                if not getattr(self, "resolved_by", None):
                    self.resolved_by = f.session.user
            f._ALERTS[self._n].update({
                "status": self.status,
                "resolution_note": getattr(self, "resolution_note", None),
                "resolved_by": getattr(self, "resolved_by", None),
                "resolved_at": getattr(self, "resolved_at", None)})
        def add_comment(self, t, txt):
            f._ALERTS[self._n].setdefault("comments", []).append(txt)

    def get_doc(dt, name=None):
        if dt == "EC Alert":
            return _AlertDoc(name)
        raise Exception("unhandled get_doc %s" % dt)

    f.get_all = get_all
    f.get_doc = get_doc
    f.log_error = lambda *a, **k: f._LOG.append(a)
    f.get_traceback = lambda: "tb"
    f.logger = lambda *a, **k: types.SimpleNamespace(warning=lambda *a, **k: None,
                                                     info=lambda *a, **k: None)
    f.utils = types.SimpleNamespace(nowdate=lambda: "2026-06-14")
    sys.modules["frappe"] = f
    return f


_FK = _install_fake_frappe()
_REAL_FRAPPE = _FK is None

import frappe  # noqa: E402
from ecentric_workspace.alerts.services import policy_scope as ps        # noqa: E402
from ecentric_workspace.alerts.services import policy_setup as pset      # noqa: E402
from ecentric_workspace.alerts.services import policy_lookup             # noqa: E402


class _FakeCaseTodo:
    def __init__(self):
        self.recomputes = []
    import contextlib

    def autosync_suspended(self):
        import contextlib
        return contextlib.nullcontext()

    def sync_brand_setup(self, brand, owner=None):
        self.recomputes.append(brand)


class _FakeLookup:
    def __init__(self):
        self.script = {}

    def find_policy(self, brand, platform=None, shop=None, item=None, seller_sku=None, on_date=None):
        nm = self.script.get((platform, shop, item, seller_sku), self.script.get("*"))
        if not nm:
            return None, None
        return types.SimpleNamespace(name=nm), 4


@unittest.skipIf(_REAL_FRAPPE, "needs the stubbed-frappe unit harness")
class TestPolicyScope(unittest.TestCase):
    def setUp(self):
        frappe._POLICIES[:] = []

    def test_scope_key(self):
        self.assertEqual(ps.scope_key("Shopee", "S1", "SKU1", "ITEM1", 0), ("Shopee", "S1", "SKU1"))
        self.assertEqual(ps.scope_key(None, "", "", "", 1), ("All", "", "__fallback__"))
        self.assertNotEqual(ps.scope_key("All", "", "SKU1", "", 0),
                            ps.scope_key("Shopee", "", "SKU1", "", 0))

    def test_find_active_conflict(self):
        frappe._POLICIES[:] = [{"name": "EC-PP-1", "brand": "B", "status": "Active",
                                "platform": "Shopee", "shop": "", "seller_sku": "SKU1",
                                "item": "", "is_brand_fallback": 0,
                                "effective_from": None, "effective_to": None}]
        self.assertEqual(ps.find_active_conflict("B", "Shopee", "", "SKU1", "", 0, None, None), "EC-PP-1")
        self.assertIsNone(ps.find_active_conflict("B", "Shopee", "", "SKU1", "", 0, None, None,
                                                  exclude_name="EC-PP-1"))
        self.assertIsNone(ps.find_active_conflict("B", "Lazada", "", "SKU1", "", 0, None, None))


@unittest.skipIf(_REAL_FRAPPE, "needs the stubbed-frappe unit harness")
class TestStep6(unittest.TestCase):
    def setUp(self):
        frappe._ALERTS.clear()
        frappe._POLICIES[:] = []
        self.ct = _FakeCaseTodo()
        self.lk = _FakeLookup()
        pset.case_todo = self.ct          # deterministic recorder
        pset.policy_lookup = self.lk

    def _policy(self, status="Active"):
        return types.SimpleNamespace(name="EC-PP-9", brand="B", status=status)

    def _alert(self, nm, sku, status="Open"):
        frappe._ALERTS[nm] = {"brand": "B", "rule_code": "missing_policy",
                              "status": status, "platform": "Shopee", "shop": "",
                              "item": None, "seller_sku": sku}

    def test_draft_is_noop(self):
        self._alert("AL1", "SKU1")
        s = pset.terminalize_for_policy(self._policy(status="Draft"))
        self.assertEqual(s["closed"], [])
        self.assertEqual(frappe._ALERTS["AL1"]["status"], "Open")

    def test_active_closes_only_covered_with_real_matched_policy(self):
        self._alert("AL1", "SKU1")
        self._alert("AL2", "SKU2")
        self.lk.script[("Shopee", "", None, "SKU1")] = "EC-PP-OTHER"   # covered by a DIFFERENT policy
        s = pset.terminalize_for_policy(self._policy())
        self.assertEqual([c["alert"] for c in s["closed"]], ["AL1"])
        self.assertEqual(s["closed"][0]["matched_policy"], "EC-PP-OTHER")   # REAL match audited
        self.assertEqual(s["skipped_no_coverage"], 1)
        self.assertEqual(frappe._ALERTS["AL1"]["status"], "Closed")
        self.assertEqual(frappe._ALERTS["AL2"]["status"], "Open")           # not covered -> stays
        self.assertIn("EC-PP-OTHER", frappe._ALERTS["AL1"]["resolution_note"])
        self.assertEqual(frappe._ALERTS["AL1"]["resolved_by"], "tester")
        self.assertEqual(self.ct.recomputes, ["B"])                         # once

    def test_idempotent_terminal_skipped(self):
        self._alert("AL1", "SKU1", status="Closed")   # already terminal -> not a candidate
        self.lk.script["*"] = "EC-PP-X"
        s = pset.terminalize_for_policy(self._policy())
        self.assertEqual(s["closed"], [])

    def test_recompute_false_for_bulk(self):
        self._alert("AL1", "SKU1")
        self.lk.script["*"] = "EC-PP-X"
        pset.terminalize_for_policy(self._policy(), recompute=False)
        self.assertEqual(self.ct.recomputes, [])       # bulk recomputes once at the end instead


class TestRowValue(unittest.TestCase):
    """_row_value must read a field from ANY row type (dict / frappe._dict /
    Document / SimpleNamespace) - the production frappe.get_all returns
    frappe._dict, the unit tests pass SimpleNamespace. Pure; not frappe-gated."""

    def test_dict_row(self):
        self.assertEqual(pset._row_value({"platform": "Shopee"}, "platform"), "Shopee")
        self.assertEqual(pset._row_value({}, "shop", "X"), "X")
        self.assertIsNone(pset._row_value({}, "shop"))

    def test_simplenamespace_row(self):
        r = types.SimpleNamespace(platform="Lazada", name="AL1")
        self.assertEqual(pset._row_value(r, "platform"), "Lazada")
        self.assertEqual(pset._row_value(r, "name"), "AL1")

    def test_object_missing_optional_returns_none(self):
        r = types.SimpleNamespace(seller_sku="SKU1")   # no shop / item
        self.assertIsNone(pset._row_value(r, "shop"))
        self.assertIsNone(pset._row_value(r, "item"))
        self.assertEqual(pset._row_value(r, "shop", "-"), "-")


if __name__ == "__main__":
    unittest.main()

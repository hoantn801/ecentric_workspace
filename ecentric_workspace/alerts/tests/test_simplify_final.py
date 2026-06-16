"""Final Price Setup / Gift Exemption simplification tests (site-free; self-stubbed).

Covers:
  * the one-time cleanup maintenance script (auth, dry-run, Active-refusal, backup)
  * Price Setup status MULTI-select -> OR ("in") semantics in list_policies
  * the missing-policy export sharing ONE canonical schema with the template download

    bench run-tests --module ecentric_workspace.alerts.tests.test_simplify_final
"""
import os
import sys
import tempfile
import types
import unittest


# --------------------------------------------------------------------------- #
# Minimal frappe stub (configurable per test via the module-level _DB).
# --------------------------------------------------------------------------- #
class _PermissionError(Exception):
    pass


class _FakeDB:
    def __init__(self):
        self.rows = {}            # name -> dict(status/brand/platform/seller_sku/...)
        self.deleted = []
        self.committed = False

    def exists(self, doctype, name):
        return name in self.rows

    def get_value(self, doctype, name, fields, as_dict=False):
        r = self.rows.get(name, {})
        if as_dict:
            return {f: r.get(f) for f in fields}
        return tuple(r.get(f) for f in fields)

    def count(self, *a, **k):
        return 0

    def commit(self):
        self.committed = True


def _install_frappe():
    if "frappe" in sys.modules:
        return sys.modules["frappe"]
    fr = types.ModuleType("frappe")
    fr.__version__ = "15.0.0"
    fr.PermissionError = _PermissionError
    fr.whitelist = lambda *a, **k: (lambda f: f)
    fr._ = lambda s: s
    fr.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a[0] if a else "throw"))
    fr.session = types.SimpleNamespace(user="Administrator")
    fr.db = _FakeDB()
    fr.get_all = lambda *a, **k: []
    fr.get_roles = lambda user=None: ["System Manager"]
    fr.get_doc = lambda *a, **k: types.SimpleNamespace(as_dict=lambda: {"name": a[1]})
    fr.delete_doc = lambda dt, name, **k: fr.db.deleted.append(name)
    fr.get_site_path = lambda *parts: os.path.join(tempfile.gettempdir(), *parts)
    fr.logger = lambda *a, **k: types.SimpleNamespace(info=lambda *a, **k: None)
    sys.modules["frappe"] = fr
    u = types.ModuleType("frappe.utils")
    u.now_datetime = lambda: __import__("datetime").datetime(2026, 6, 16, 12, 0, 0)
    u.nowdate = lambda: "2026-06-16"
    u.cint = lambda v, default=0: int(v) if str(v).strip() not in ("", "None") else default
    sys.modules["frappe.utils"] = u
    return fr


_FR = _install_frappe()
_DB = _FR.db


# --------------------------------------------------------------------------- #
# B. One-time cleanup maintenance script
# --------------------------------------------------------------------------- #
from ecentric_workspace.alerts.maintenance import cleanup_test_policies as ctp  # noqa: E402


class TestCleanupScript(unittest.TestCase):
    def setUp(self):
        _DB.rows = {
            "EC-PP-1": {"name": "EC-PP-1", "status": "Draft", "brand": "B", "platform": "Shopee",
                        "seller_sku": "S1", "creation": "2026-01-01", "modified": "2026-02-01"},
            "EC-PP-2": {"name": "EC-PP-2", "status": "Active", "brand": "B", "platform": "Shopee",
                        "seller_sku": "S2", "creation": "2026-01-01", "modified": "2026-02-01"},
            "EC-PP-3": {"name": "EC-PP-3", "status": "Inactive", "brand": "B", "platform": "Lazada",
                        "seller_sku": "S3", "creation": "2026-01-01", "modified": "2026-02-01"},
        }
        _DB.deleted = []
        _DB.committed = False
        _FR.session.user = "Administrator"
        _FR.get_roles = lambda user=None: ["System Manager"]

    def test_plan_refuses_active(self):
        docs = [{"name": "a", "status": "Draft"}, {"name": "b", "status": "Active"},
                {"name": "c", "status": "Inactive"}]
        deletable, blocked = ctp.plan_deletions(docs)
        self.assertEqual([d["name"] for d in deletable], ["a", "c"])
        self.assertEqual([d["name"] for d in blocked], ["b"])

    def test_normalize_names_accepts_str_or_list(self):
        self.assertEqual(ctp._normalize_names("EC-PP-1, EC-PP-2 ,"), ["EC-PP-1", "EC-PP-2"])
        self.assertEqual(ctp._normalize_names(["EC-PP-1", "", "EC-PP-2"]), ["EC-PP-1", "EC-PP-2"])

    def test_unauthorized_execution_rejected(self):
        _FR.session.user = "kam@example.com"
        _FR.get_roles = lambda user=None: ["Alert KAM"]      # NOT System Manager
        with self.assertRaises(_PermissionError):
            ctp.run(names=["EC-PP-1"], execute=True)
        self.assertEqual(_DB.deleted, [])                    # nothing deleted

    def test_dry_run_deletes_nothing(self):
        res = ctp.run(names=["EC-PP-1", "EC-PP-3"])          # execute defaults False
        self.assertTrue(res["dry_run"])
        self.assertEqual(res["deleted"], [])
        self.assertEqual(_DB.deleted, [])
        self.assertEqual(set(res["deletable"]), {"EC-PP-1", "EC-PP-3"})

    def test_active_cannot_be_purged_even_on_execute(self):
        res = ctp.run(names=["EC-PP-1", "EC-PP-2", "EC-PP-3"], execute=True,
                      backup_dir=tempfile.mkdtemp())
        self.assertIn("EC-PP-2", res["blocked_active"])      # Active refused
        self.assertNotIn("EC-PP-2", _DB.deleted)
        self.assertEqual(set(_DB.deleted), {"EC-PP-1", "EC-PP-3"})
        self.assertTrue(_DB.committed)

    def test_execute_writes_backup_before_delete(self):
        d = tempfile.mkdtemp()
        res = ctp.run(names=["EC-PP-1"], execute=True, backup_dir=d)
        self.assertTrue(res["backup_file"] and os.path.exists(res["backup_file"]))
        self.assertEqual(_DB.deleted, ["EC-PP-1"])


# --------------------------------------------------------------------------- #
# C + A. list_policies status OR + missing-policy export shared schema.
# These need api_policies, whose sibling service imports are stubbed empty so the
# module imports without a site (list_policies/missing_policy_csv only use frappe +
# perms + the REAL policy_csv).
# --------------------------------------------------------------------------- #
for _m in ("policy_validation", "policy_scope", "policy_setup", "case_todo",
           "case_lifecycle", "policy_coverage"):
    _name = "ecentric_workspace.alerts.services." + _m
    if _name not in sys.modules:
        sys.modules[_name] = types.ModuleType(_name)

if "ecentric_workspace.alerts.permissions" not in sys.modules:
    _perms = types.ModuleType("ecentric_workspace.alerts.permissions")
    _perms.ALL_BRANDS = "*"
    _perms._allowed = "*"
    _perms.require_alert_center_access = lambda *a, **k: _perms._allowed
    _perms.require_brand_access = lambda *a, **k: None
    _perms.can_manage_policy = lambda *a, **k: True
    sys.modules["ecentric_workspace.alerts.permissions"] = _perms
_PERMS = sys.modules["ecentric_workspace.alerts.permissions"]

from ecentric_workspace.alerts import api_policies as ap  # noqa: E402


class TestStatusMultiSelect(unittest.TestCase):
    def setUp(self):
        self._cap = {}
        _PERMS._allowed = _PERMS.ALL_BRANDS

        def _ga(*a, **k):
            self._cap["filters"] = k.get("filters")
            return []
        _FR.get_all = _ga

    def _clauses(self):
        return self._cap.get("filters") or []

    def test_multi_status_uses_in_or_semantics(self):
        ap.list_policies(filters={"status": ["Active", "Paused", "Draft"]})
        self.assertIn(["status", "in", ["Active", "Paused", "Draft"]], self._clauses())

    def test_single_status_string_stays_equality(self):
        ap.list_policies(filters={"status": "Active"})
        self.assertIn(["status", "=", "Active"], self._clauses())

    def test_empty_status_adds_no_status_clause(self):
        ap.list_policies(filters={"status": []})
        self.assertFalse([c for c in self._clauses() if c[0] == "status"])


class TestMissingExportSharedSchema(unittest.TestCase):
    def setUp(self):
        _PERMS._allowed = _PERMS.ALL_BRANDS
        sku = types.ModuleType("ecentric_workspace.alerts.api_sku_catalog")
        sku.policy_missing_skus = lambda brand, platform=None, days=30, limit=200: {
            "missing": [{"seller_sku": "S1", "product_name": "Prod 1"},
                        {"seller_sku": "S2", "product_name": "Prod 2"}]}
        sys.modules["ecentric_workspace.alerts.api_sku_catalog"] = sku

    def test_export_uses_canonical_header_and_prefill(self):
        from ecentric_workspace.alerts.services import policy_csv
        out = ap.missing_policy_csv("BRAND-X")
        lines = out["content"].strip("\n").split("\n")
        # SAME header as the template download (single shared helper).
        self.assertEqual(lines[0], policy_csv.template_csv().strip("\n"))
        self.assertEqual(lines[0],
                         "brand,platform,seller_sku,product_name,min_price,"
                         "target_price,reference_price,status,is_gift")
        # brand/seller_sku/product_name pre-filled; price/status/is_gift blank.
        self.assertEqual(lines[1], "BRAND-X,,S1,Prod 1,,,,,")
        self.assertEqual(lines[2], "BRAND-X,,S2,Prod 2,,,,,")
        self.assertTrue(out["filename"].endswith("BRAND-X.csv"))


if __name__ == "__main__":
    unittest.main()

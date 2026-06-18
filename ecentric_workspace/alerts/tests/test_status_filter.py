"""Hotfix: Price Setup status MULTI-select filtering.

Root cause covered here: the multi-select frontend sends several statuses, but the old
backend compared `status` with a single `=` (and only a Python list was ever unit-tested).
`_normalize_statuses` now accepts every shape the client may send and the filter is applied
with OR semantics, so selecting Active/Paused/Expired never leaks Inactive rows.

    bench run-tests --module ecentric_workspace.alerts.tests.test_status_filter
"""
import sys
import types
import unittest


# --- minimal frappe + sibling-module stubs so api_policies imports without a site ----- #
if "frappe" not in sys.modules:
    fr = types.ModuleType("frappe")
    fr.whitelist = lambda *a, **k: (lambda f: f)
    fr._ = lambda s: s
    fr.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a[0] if a else "throw"))
    fr.session = types.SimpleNamespace(user="tester")
    fr.PermissionError = type("PermissionError", (Exception,), {})

    class _DB:
        def count(self, *a, **k):
            return 0
    fr.db = _DB()
    fr.get_all = lambda *a, **k: []
    sys.modules["frappe"] = fr
    u = types.ModuleType("frappe.utils")
    u.cint = lambda v, default=0: int(v) if str(v).strip() not in ("", "None") else default
    u.now_datetime = lambda: None
    sys.modules["frappe.utils"] = u

_SVC = "ecentric_workspace.alerts.services"
if _SVC not in sys.modules:                      # parent package (frappe-free sandbox only)
    _pkg = types.ModuleType(_SVC)
    _pkg.__path__ = []
    sys.modules[_SVC] = _pkg
for _m in ("policy_validation", "policy_scope", "policy_setup", "case_todo",
           "case_lifecycle", "policy_coverage", "policy_csv"):
    _n = _SVC + "." + _m
    if _n not in sys.modules:
        _sm = types.ModuleType(_n)
        sys.modules[_n] = _sm
        setattr(sys.modules[_SVC], _m, _sm)      # so `from ...services import X` resolves

if "ecentric_workspace.alerts.permissions" not in sys.modules:
    _p = types.ModuleType("ecentric_workspace.alerts.permissions")
    _p.ALL_BRANDS = "*"
    _p._allowed = "*"
    _p.require_alert_center_access = lambda *a, **k: _p._allowed
    sys.modules["ecentric_workspace.alerts.permissions"] = _p
_PERMS = sys.modules["ecentric_workspace.alerts.permissions"]

from ecentric_workspace.alerts import api_policies as ap  # noqa: E402
import frappe  # noqa: E402


class TestNormalizeStatuses(unittest.TestCase):
    def test_list(self):
        self.assertEqual(ap._normalize_statuses(["Active", "Paused"]), ["Active", "Paused"])

    def test_tuple_and_set(self):
        self.assertEqual(ap._normalize_statuses(("Active", "Paused")), ["Active", "Paused"])
        self.assertEqual(sorted(ap._normalize_statuses({"Active", "Paused"})),
                         ["Active", "Paused"])

    def test_json_array_string(self):
        self.assertEqual(ap._normalize_statuses('["Active","Paused","Expired"]'),
                         ["Active", "Paused", "Expired"])

    def test_comma_separated_string(self):
        self.assertEqual(ap._normalize_statuses("Active, Paused ,Expired"),
                         ["Active", "Paused", "Expired"])

    def test_single_string(self):
        self.assertEqual(ap._normalize_statuses("Active"), ["Active"])

    def test_empty_inputs(self):
        for v in (None, "", "   ", [], (), set(), "[]"):
            self.assertEqual(ap._normalize_statuses(v), [], repr(v))

    def test_dedup_and_blank_strip(self):
        self.assertEqual(ap._normalize_statuses("Active,Active, ,Paused"),
                         ["Active", "Paused"])
        self.assertEqual(ap._normalize_statuses(["Active", "", "Active", "Paused"]),
                         ["Active", "Paused"])

    def test_malformed_json_falls_back_to_csv(self):
        self.assertEqual(ap._normalize_statuses("[Active,Paused"), ["[Active", "Paused"])


class TestListPoliciesStatusFilter(unittest.TestCase):
    def setUp(self):
        _PERMS._allowed = _PERMS.ALL_BRANDS
        self.cap = {}

        def _ga(*a, **k):
            self.cap["filters"] = k.get("filters")
            return []
        frappe.get_all = _ga

    def _status_clause(self):
        for c in (self.cap.get("filters") or []):
            if c and c[0] == "status":
                return c
        return None

    def _run(self, status):
        ap.list_policies(filters={"status": status})
        return self._status_clause()

    def test_all_four_formats_produce_in_clause(self):
        for status in (["Active", "Paused", "Expired"],          # list
                       ("Active", "Paused", "Expired"),          # tuple
                       '["Active","Paused","Expired"]',          # JSON array string
                       "Active,Paused,Expired"):                 # comma-separated string
            clause = self._run(status)
            self.assertIsNotNone(clause, repr(status))
            self.assertEqual(clause[0], "status")
            self.assertEqual(clause[1], "in")                    # OR semantics, never "="
            self.assertEqual(set(clause[2]), {"Active", "Paused", "Expired"})

    def test_single_status_still_in_clause(self):
        clause = self._run("Active")
        self.assertEqual(clause, ["status", "in", ["Active"]])

    def test_selected_excludes_inactive(self):
        # the reported bug: Active/Paused/Expired must NOT return Inactive rows.
        clause = self._run('["Active","Paused","Expired"]')
        self.assertNotIn("Inactive", clause[2])

    def test_empty_status_adds_no_clause(self):
        for status in ([], "", None, "[]"):
            self.assertIsNone(self._run(status), repr(status))


if __name__ == "__main__":
    unittest.main()

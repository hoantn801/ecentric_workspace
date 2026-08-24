# Copyright (c) 2026, eCentric and contributors
"""reporting.actions: the hub routes an action on an EC Approval Request to the SAME facade
the form pages use (resolve approval_type -> registry definition -> facade). It must never
re-implement the rules, and must fail loudly on an unknown/unregistered request."""
import sys
import types
import unittest


def _boot():
    if "frappe" not in sys.modules:
        f = types.ModuleType("frappe"); f.__path__ = []
        f._ = lambda s: s
        f.whitelist = lambda *a, **k: (lambda fn: fn)
        f.DoesNotExistError = type("DoesNotExistError", (Exception,), {})
        def _throw(msg, exc=None):
            raise (exc or Exception)(msg)
        f.throw = _throw
        f.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
        f.session = types.SimpleNamespace(user="u@e.c")
        u = types.ModuleType("frappe.utils"); u.now_datetime = lambda *a, **k: None
        sys.modules["frappe"] = f; sys.modules["frappe.utils"] = u
    from ecentric_workspace.approval_center.reporting import actions as a
    return a


class _D(dict):
    __getattr__ = lambda self, k: self.get(k)


class TestHubActions(unittest.TestCase):
    def setUp(self):
        self.a = _boot()
        self._frappe = self.a.frappe
        self._facade = self.a.APPROVAL_FACADE
        self._get = self.a.get_definition

    def tearDown(self):
        self.a.frappe = self._frappe
        self.a.APPROVAL_FACADE = self._facade
        self.a.get_definition = self._get

    def _stub(self, row):
        fr = types.ModuleType("frappe")
        fr._ = lambda s: s
        fr.DoesNotExistError = type("DoesNotExistError", (Exception,), {})
        def _throw(msg, exc=None):
            raise (exc or Exception)(msg)
        fr.throw = _throw
        fr.db = types.SimpleNamespace(get_value=lambda *a, **k: row)
        self.a.frappe = fr
        self.calls = []
        self.a.get_definition = lambda code: "DEF:" + code
        self.a.APPROVAL_FACADE = types.SimpleNamespace(
            approve=lambda d, n, c=None: self.calls.append(("approve", d, n, c)),
            reject=lambda d, n, c=None: self.calls.append(("reject", d, n, c)),
            request_information=lambda d, n, c=None: self.calls.append(("info", d, n, c)),
            claim_fulfillment=lambda d, n: self.calls.append(("claim", d, n)))

    def test_approve_routes_to_facade_with_business_name(self):
        self._stub(_D({"approval_type": "SYSTEM_REQUEST", "reference_doctype": "EC System Request",
                       "reference_name": "EC-SYSR-13"}))
        self.a.approve("EC-APR-60", comment="ok")
        self.assertEqual(self.calls, [("approve", "DEF:SYSTEM_REQUEST", "EC-SYSR-13", "ok")])

    def test_claim_routes_to_facade(self):
        self._stub(_D({"approval_type": "ASSET_REQUEST", "reference_doctype": "EC Asset Request",
                       "reference_name": "EC-ASSR-3"}))
        self.a.claim_fulfillment("EC-APR-61")
        self.assertEqual(self.calls, [("claim", "DEF:ASSET_REQUEST", "EC-ASSR-3")])

    def test_unknown_request_raises(self):
        self._stub(None)
        with self.assertRaises(Exception):
            self.a.approve("EC-APR-999")

    def test_unregistered_type_raises(self):
        self._stub(_D({"approval_type": "NOPE", "reference_doctype": "X", "reference_name": "N1"}))
        def _boom(code):
            raise KeyError(code)
        self.a.get_definition = _boom
        with self.assertRaises(Exception):
            self.a.approve("EC-APR-62")


if __name__ == "__main__":
    unittest.main()

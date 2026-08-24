# Copyright (c) 2026, eCentric and contributors
"""bootstrap() must expose tabs.fulfillment.

The form pages gate their Operation/fulfillment tab on tabs.fulfillment. Only ai_topup
(bespoke controller) set it; the shared bootstrap did not, so once the other forms moved
onto the shared adapter the tab vanished and an approved request could never be claimed
(observed: EC-SYSR-2026-00013 sat in 'Chờ Operation nhận xử lý' with no action for anyone,
while list_fulfillment_queue still returned it). Site-free: monkeypatch module frappe."""
import sys
import types
import unittest


def _load():
    if "frappe" not in sys.modules:
        f = types.ModuleType("frappe"); f.__path__ = []
        f._ = lambda s: s
        f.session = types.SimpleNamespace(user="u@e.c")
        f.db = types.SimpleNamespace(exists=lambda *a, **k: False, get_value=lambda *a, **k: None,
                                     count=lambda *a, **k: 0)
        f.get_all = lambda *a, **k: []
        f.get_roles = lambda *a, **k: []
        f.parse_json = lambda x: x
        u = types.ModuleType("frappe.utils"); u.now_datetime = lambda *a, **k: None
        sys.modules["frappe"] = f; sys.modules["frappe.utils"] = u
    from ecentric_workspace.approval_center.shared.requests import query_service as q
    return q


class _Def:
    code = "SYSTEM_REQUEST"
    business_doctype = "EC System Request"
    options_provider = staticmethod(lambda: {})


class TestBootstrapFulfillmentTab(unittest.TestCase):
    def setUp(self):
        self.q = _load()
        self._frappe = self.q.frappe
        self._ctx = self.q.employee_context
        self._can = self.q._can_fulfil
        self.q.employee_context = lambda user: {"user": user}

    def tearDown(self):
        self.q.frappe = self._frappe
        self.q.employee_context = self._ctx
        self.q._can_fulfil = self._can

    def _stub_frappe(self, roles=()):
        fr = types.ModuleType("frappe")
        fr.session = types.SimpleNamespace(user="u@e.c")
        fr.get_roles = lambda user=None: list(roles)
        fr.db = types.SimpleNamespace(exists=lambda *a, **k: False)
        self.q.frappe = fr
        self.q.capabilities.frappe = fr

    def test_tab_true_for_eligible_fulfiller(self):
        self._stub_frappe()
        self.q._can_fulfil = lambda user, definition: True
        out = self.q.bootstrap(_Def())
        self.assertIn("fulfillment", out["tabs"])
        self.assertTrue(out["tabs"]["fulfillment"])

    def test_tab_false_for_non_fulfiller(self):
        self._stub_frappe()
        self.q._can_fulfil = lambda user, definition: False
        out = self.q.bootstrap(_Def())
        self.assertFalse(out["tabs"]["fulfillment"])

    def test_can_fulfil_never_raises(self):
        # permissions blowing up must hide the tab, not break the page
        self._stub_frappe()
        out = self.q._can_fulfil(None, _Def())
        self.assertIn(out, (True, False))


if __name__ == "__main__":
    unittest.main()

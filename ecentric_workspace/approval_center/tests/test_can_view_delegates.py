# Copyright (c) 2026, eCentric and contributors
"""Bug guard: capabilities.can_view must delegate to the canonical can_view_request
(single source of truth), so form detail agrees with the Action Center feed and the
fulfillment_owner / eligible fulfiller are allowed to open a request they were assigned.

Site-free: minimal frappe stub for import; can_view_request is spied so we assert the
forwarded arguments (not the DB logic)."""
import sys
import types
import unittest


def _ensure_frappe():
    if "frappe" not in sys.modules:
        f = types.ModuleType("frappe")
        f.__path__ = []
        f.get_roles = lambda user=None: []
        f.db = types.SimpleNamespace(exists=lambda *a, **k: False,
                                     get_value=lambda *a, **k: None)
        f.session = types.SimpleNamespace(user="x@e.c")
        sys.modules["frappe"] = f


class _Dict(dict):
    __getattr__ = lambda self, k: self.get(k)


class TestCanViewDelegates(unittest.TestCase):
    def setUp(self):
        _ensure_frappe()
        from ecentric_workspace.approval_center.shared.requests import capabilities as cap
        self.cap = cap
        self._orig = cap.can_view_request
        self.calls = []
        cap.can_view_request = lambda *a, **k: (self.calls.append((a, k)) or True)

    def tearDown(self):
        self.cap.can_view_request = self._orig

    def test_forwards_all_canonical_args(self):
        biz = types.SimpleNamespace(doctype="EC Asset Request",
                                    requested_by="req@e.c",
                                    fulfillment_owner="owner@e.c")
        req = _Dict(name="EC-APR-1", approval_type="ASSET_REQUEST")
        out = self.cap.can_view("owner@e.c", biz, req)
        self.assertTrue(out)
        (args, kw) = self.calls[0]
        self.assertEqual(args[0], "EC-APR-1")            # request_name
        self.assertEqual(args[1], "owner@e.c")           # user
        self.assertEqual(kw["business_doctype"], "EC Asset Request")
        self.assertEqual(kw["requested_by"], "req@e.c")
        self.assertEqual(kw["fulfillment_owner"], "owner@e.c")
        self.assertEqual(kw["approval_type"], "ASSET_REQUEST")

    def test_no_request_and_no_fulfillment_field(self):
        biz = types.SimpleNamespace(doctype="EC Leave Request", requested_by="a@e.c")
        self.cap.can_view("a@e.c", biz, None)
        (args, kw) = self.calls[0]
        self.assertIsNone(args[0])                        # request_name None
        self.assertIsNone(kw["fulfillment_owner"])        # getattr -> None (no field)
        self.assertIsNone(kw["approval_type"])            # no request


if __name__ == "__main__":
    unittest.main()

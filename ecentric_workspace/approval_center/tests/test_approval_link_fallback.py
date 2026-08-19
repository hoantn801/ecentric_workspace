# Copyright (c) 2026, eCentric and contributors
"""_approval_link must not return an empty deep link when the business doc doesn't carry
approval_type: it falls back to the linked EC Approval Request (authoritative). Root cause
of blank 'Link:' Teams cards. Site-free: monkeypatch transitions.frappe."""
import sys
import types
import unittest


def _load():
    if "frappe" not in sys.modules:
        f = types.ModuleType("frappe"); f.__path__ = []
        f._ = lambda s: s
        f.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
        f.utils = types.SimpleNamespace(get_url=lambda: "https://team.ecentric.vn")
        u = types.ModuleType("frappe.utils")
        u.now_datetime = lambda *a, **k: None; u.add_to_date = lambda *a, **k: None
        u.getdate = lambda *a, **k: None; u.get_url = lambda: "https://team.ecentric.vn"
        sys.modules["frappe"] = f; sys.modules["frappe.utils"] = u
    from ecentric_workspace.approval_center.shared.workflow import transitions as t
    return t


class TestApprovalLinkFallback(unittest.TestCase):
    def setUp(self):
        self.t = _load()
        self._orig = self.t.frappe

    def tearDown(self):
        self.t.frappe = self._orig

    def _stub(self, store):
        fr = types.ModuleType("frappe")
        fr.get_value = None
        def gv(dt, name, field):
            return store.get((dt, name, field))
        fr.db = types.SimpleNamespace(get_value=gv)
        fr.utils = types.SimpleNamespace(get_url=lambda: "https://team.ecentric.vn")
        self.t.frappe = fr

    def test_falls_back_to_approval_request(self):
        # business doc has NO approval_type value; linked request does
        self._stub({
            ("EC System Request", "EC-SYSR-9", "approval_type"): None,
            ("EC System Request", "EC-SYSR-9", "approval_request"): "APR-9",
            ("EC Approval Request", "APR-9", "approval_type"): "SYSTEM_REQUEST",
            ("EC Approval Type", "SYSTEM_REQUEST", "route"): "approvals/system-request",
        })
        out = self.t._approval_link("EC System Request", "EC-SYSR-9")
        self.assertEqual(out, "https://team.ecentric.vn/approvals/system-request?id=EC-SYSR-9")

    def test_uses_business_doc_when_present(self):
        self._stub({
            ("EC AI Topup Request", "EC-AITOP-6", "approval_type"): "AI_TOPUP",
            ("EC Approval Type", "AI_TOPUP", "route"): "approvals/ai-topup",
        })
        out = self.t._approval_link("EC AI Topup Request", "EC-AITOP-6")
        self.assertEqual(out, "https://team.ecentric.vn/approvals/ai-topup?id=EC-AITOP-6")

    def test_none_when_no_route_anywhere(self):
        self._stub({
            ("EC X", "N1", "approval_type"): None,
            ("EC X", "N1", "approval_request"): None,
        })
        self.assertIsNone(self.t._approval_link("EC X", "N1"))


if __name__ == "__main__":
    unittest.main()

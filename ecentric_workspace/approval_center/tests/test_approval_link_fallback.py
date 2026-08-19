# Copyright (c) 2026, eCentric and contributors
"""_approval_link must not return an empty deep link. The business doc often lacks
approval_type AND its approval_request back-link is not set yet at notify time, so the
link is derived by REVERSE-LOOKING-UP the EC Approval Request by reference. Root cause of
blank 'Link:' Teams cards. Site-free: monkeypatch transitions.frappe."""
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


class TestApprovalLink(unittest.TestCase):
    def setUp(self):
        self.t = _load()
        self._orig = self.t.frappe

    def tearDown(self):
        self.t.frappe = self._orig

    def _stub(self, doc_atype, reverse_atype, route):
        fr = types.ModuleType("frappe")
        def gv(dt, key, field):
            # business doc approval_type (key is a name string)
            if dt != "EC Approval Request" and dt != "EC Approval Type" and field == "approval_type":
                return doc_atype
            # reverse lookup: EC Approval Request by reference dict -> approval_type
            if dt == "EC Approval Request" and isinstance(key, dict) and field == "approval_type":
                return reverse_atype
            # route
            if dt == "EC Approval Type" and field == "route":
                return route
            return None
        fr.db = types.SimpleNamespace(get_value=gv)
        fr.utils = types.SimpleNamespace(get_url=lambda: "https://team.ecentric.vn")
        self.t.frappe = fr

    def test_reverse_lookup_when_business_doc_empty(self):
        # business doc approval_type None (and back-link unset) -> reverse lookup finds type
        self._stub(doc_atype=None, reverse_atype="SYSTEM_REQUEST", route="/approvals/system-request")
        out = self.t._approval_link("EC System Request", "EC-SYSR-12")
        self.assertEqual(out, "https://team.ecentric.vn/approvals/system-request?id=EC-SYSR-12")

    def test_uses_business_doc_when_present(self):
        self._stub(doc_atype="AI_TOPUP", reverse_atype=None, route="/approvals/ai-topup")
        out = self.t._approval_link("EC AI Topup Request", "EC-AITOP-6")
        self.assertEqual(out, "https://team.ecentric.vn/approvals/ai-topup?id=EC-AITOP-6")

    def test_none_when_no_type_anywhere(self):
        self._stub(doc_atype=None, reverse_atype=None, route=None)
        self.assertIsNone(self.t._approval_link("EC X", "N1"))

    def test_prefixes_slash_if_missing(self):
        self._stub(doc_atype="SYSTEM_REQUEST", reverse_atype=None, route="approvals/system-request")
        out = self.t._approval_link("EC System Request", "EC-SYSR-12")
        self.assertEqual(out, "https://team.ecentric.vn/approvals/system-request?id=EC-SYSR-12")


if __name__ == "__main__":
    unittest.main()

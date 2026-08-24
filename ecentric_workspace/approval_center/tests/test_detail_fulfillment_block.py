# Copyright (c) 2026, eCentric and contributors
"""detail() must return a `fulfillment` block, and derive() must expose can_claim /
can_complete, so an approved request can be picked up from its detail page.

Observed: EC-SYSR-2026-00013 showed 'Trạng thái xử lý: —' and 'Không có hành động khả dụng'
for everyone, because only ai_topup's bespoke controller returned det.fulfillment and the
claim capability; the shared adapter (system/asset/data/document/resignation...) did not."""
import sys
import types
import unittest


def _boot_frappe():
    if "frappe" not in sys.modules:
        f = types.ModuleType("frappe"); f.__path__ = []
        f._ = lambda s: s
        f.session = types.SimpleNamespace(user="u@e.c")
        f.db = types.SimpleNamespace(exists=lambda *a, **k: False, get_value=lambda *a, **k: None,
                                     count=lambda *a, **k: 0)
        f.get_all = lambda *a, **k: []
        f.get_roles = lambda *a, **k: []
        f.get_doc = lambda *a, **k: None
        f.parse_json = lambda x: x
        u = types.ModuleType("frappe.utils"); u.now_datetime = lambda *a, **k: None
        sys.modules["frappe"] = f; sys.modules["frappe.utils"] = u


class _Biz(dict):
    doctype = "EC System Request"

    def __init__(self, fields, values):
        super().__init__(values)
        self.meta = types.SimpleNamespace(
            fields=[types.SimpleNamespace(fieldname=f) for f in fields])
        for k, v in values.items():
            setattr(self, k, v)

    def get(self, k, default=None):
        return dict.get(self, k, default)


_FF_FIELDS = ["fulfillment_status", "fulfillment_owner", "fulfillment_due_at",
              "completed_by", "completed_at", "fulfillment_summary", "output_link",
              "completed_attachment", "requested_by"]


class TestFulfillmentBlock(unittest.TestCase):
    def setUp(self):
        _boot_frappe()
        from ecentric_workspace.approval_center.shared.requests import query_service as q
        from ecentric_workspace.approval_center.shared.requests import capabilities as c
        self.q, self.c = q, c

    def test_block_returned_for_fulfillment_form(self):
        biz = _Biz(_FF_FIELDS, {"fulfillment_status": "Assigned", "fulfillment_owner": None,
                                "requested_by": "req@e.c"})
        out = self.q.fulfillment_block(biz, None)
        self.assertEqual(out["status"], "Assigned")
        self.assertIn("eligible_fulfillers", out)

    def test_empty_for_form_without_fulfillment(self):
        biz = _Biz(["requested_by", "title"], {"requested_by": "a@e.c"})
        self.assertEqual(self.q.fulfillment_block(biz, None), {})

    def test_can_claim_only_when_assigned_and_eligible(self):
        biz = _Biz(_FF_FIELDS, {"fulfillment_status": "Assigned", "requested_by": "r@e.c"})
        self.c._is_fulfiller = lambda user, doc, req=None: True
        self.assertTrue(self.c._can_claim("u@e.c", biz, None))
        biz2 = _Biz(_FF_FIELDS, {"fulfillment_status": "In Progress", "requested_by": "r@e.c"})
        self.assertFalse(self.c._can_claim("u@e.c", biz2, None))

    def test_can_complete_for_owner_only(self):
        biz = _Biz(_FF_FIELDS, {"fulfillment_status": "In Progress", "fulfillment_owner": "u@e.c"})
        self.c.is_system_manager = lambda user=None: False
        self.assertTrue(self.c._can_complete("u@e.c", biz))
        self.assertFalse(self.c._can_complete("other@e.c", biz))


if __name__ == "__main__":
    unittest.main()

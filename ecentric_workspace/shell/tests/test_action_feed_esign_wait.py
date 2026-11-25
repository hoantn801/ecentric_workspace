"""25/11/2026 (PO): phieu toi da bam "Duyet & Ky" va dang cho cong ky xac nhan -> KHONG hien o Viec cua toi,
KHONG tinh vao so "Cho toi duyet" (source_counts.approval). Cong bao loi han / cap bi tra lai -> het
"dang bay" -> hien lai. Nguon that: approval_center.shared.requests.esign_wait (in_flight_leg).
Chay: python -m pytest ecentric_workspace/shell/tests/test_action_feed_esign_wait.py
"""
import unittest

from ecentric_workspace.shell.tests import test_action_feed as base
from ecentric_workspace.shell.tests.test_action_feed import FK, _todo, feed  # noqa: F401
from ecentric_workspace.approval_center.shared.requests import esign_wait


class TestEsignWaitHidden(base.TestApprovalNormalization):
    def setUp(self):
        super().setUp()
        self._orig = esign_wait.waiting_requests
        self.asked = []

        def fake(user, levels):
            self.asked.append((user, dict(levels)))
            return set(self.waiting)
        self.waiting = set()
        esign_wait.waiting_requests = fake

    def tearDown(self):
        esign_wait.waiting_requests = self._orig

    def _graph(self):
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz_rows(self.AITOP, "EC-AITOP-1", "REQ-1", fulfillment_owner="")
        self._request("REQ-1", status="Pending", level=2, atype="AITOP",
                      requested_by="u@e.c", reference_name="EC-AITOP-1")
        self._type("AITOP", "/approvals/ai-topup")
        self._level("REQ-1", 2, "In Progress", "2026-07-20 09:00:00")

    def test_dang_cho_cong_khong_hien_khong_dem(self):
        self._graph()
        self.waiting = {"REQ-1"}
        res = feed.build_feed("u@e.c", limit=20)
        self.assertIsNone(self._find(res, "t"))
        self.assertEqual(res["source_counts"].get("approval", 0), 0)
        self.assertEqual(self.asked, [("u@e.c", {"REQ-1": 2})])

    def test_het_dang_bay_thi_hien_lai(self):
        self._graph()
        self.waiting = set()           # Permanent Failure / tra lai -> in_flight_leg None
        res = feed.build_feed("u@e.c", limit=20)
        self.assertIsNotNone(self._find(res, "t"))
        self.assertEqual(res["source_counts"].get("approval", 0), 1)

    def test_phieu_da_xong_khong_hoi_cong(self):
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz_rows(self.AITOP, "EC-AITOP-1", "REQ-1", fulfillment_owner="")
        self._request("REQ-1", status="Rejected", level=2, atype="AITOP",
                      requested_by="u@e.c", reference_name="EC-AITOP-1")
        self._type("AITOP", "/approvals/ai-topup")
        feed.build_feed("u@e.c", limit=20)
        self.assertEqual(self.asked, [("u@e.c", {})])


# Khong chay lai cac test cua lop cha o file nay.
for _n in [n for n in dir(base.TestApprovalNormalization) if n.startswith("test_")]:
    if _n not in TestEsignWaitHidden.__dict__:
        setattr(TestEsignWaitHidden, _n, None)

if __name__ == "__main__":
    unittest.main()

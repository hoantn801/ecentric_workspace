# -*- coding: utf-8 -*-
"""QC round 1 (15/11/2026) - Việc cần làm backend: lỗi tìm được + test tái hiện.

  Q1 "Việc tôi giao" lấy cả việc mình chỉ XIN DỜI HẠN (PM Assignment Request kind=Deadline,
     requested_by = người nhận) -> việc người khác giao cho mình + đồng nghiệp hiện như việc mình giao.
  Q2 N+1: việc do quy tắc lặp tạo (owner Administrator) -> givers_map gọi db.get_value từng dòng.
  Q3 Tin 08:30 khi chỉ có việc chờ nhận: "Hôm nay có 0 việc cần xử lý".
  Q4 Thứ tự hai việc cùng nhóm / ưu tiên / hạn / giờ phải ổn định (không đổi theo `modified`).
Fake 'now' = Fri 2026-10-16 10:00 (_pm_fake)."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.q = self.fk.load("ecentric_workspace.pm.api.queue")

    def me(self, u=F.ALICE):
        self.fk.set_user(u)


class TestGivenTabScope(Base):
    def test_deadline_request_does_not_make_me_the_giver(self):
        # GIVER giao cho ALICE + BOB; ALICE xin dời hạn và được chấp nhận (kind=Deadline)
        F.task(self.fk, "SHARED", owner=F.GIVER, assign=[F.ALICE, F.BOB], end="2026-10-20")
        self.fk.add("PM Assignment Request", name="DL1", task="SHARED", recipient=F.GIVER,
                    requested_by=F.ALICE, status="Accepted", kind="Deadline")
        F.task(self.fk, "MINE", owner=F.ALICE, assign=[F.BOB], end="2026-10-20")
        self.me()
        names = [r["name"] for r in self.q.list(tab="give")["rows"]]
        self.assertEqual(names, ["MINE"])

    def test_accepted_assignment_request_still_counts(self):
        # việc qua "Cần đồng ý" ALICE yêu cầu (owner khác) vẫn là việc ALICE giao
        F.task(self.fk, "VIA_REQ", owner=F.GIVER, assign=[F.BOB], end="2026-10-20")
        self.fk.add("PM Assignment Request", name="AR1", task="VIA_REQ", recipient=F.BOB,
                    requested_by=F.ALICE, status="Accepted", kind="Assignment")
        self.me()
        rows = self.q.list(tab="give")["rows"]
        self.assertEqual([(r["name"], r["giver"]) for r in rows], [("VIA_REQ", F.ALICE)])


class TestNoNPlusOne(Base):
    def test_500_recurrence_rows_constant_queries(self):
        for i in range(500):
            F.task(self.fk, "R%03d" % i, owner="Administrator", assign=[F.ALICE],
                   end="2026-10-%02d" % (10 + i % 15), priority=("High", "Low")[i % 2])
        self.fk.add("PM Recurrence", name="RULE1", owner=F.GIVER, last_task="R007")
        calls = {"get_value": 0, "get_all": 0}
        gv, ga = self.fk.db.get_value, self.fk.module.get_all

        def cgv(*a, **k):
            calls["get_value"] += 1
            return gv(*a, **k)

        def cga(*a, **k):
            calls["get_all"] += 1
            return ga(*a, **k)
        self.fk.db.get_value = cgv
        self.fk.module.get_all = cga
        self.me()
        out = self.q.list()
        self.assertEqual(len(out["rows"]), 500)
        self.assertLessEqual(calls["get_value"], 5, calls)
        self.assertLessEqual(calls["get_all"], 15, calls)
        g = {r["name"]: r["giver"] for r in out["rows"]}
        self.assertEqual(g["R007"], F.GIVER)            # quy tắc lặp -> chủ quy tắc
        self.assertEqual(g["R008"], "Administrator")    # không tìm được -> như cũ (owner)

    def test_recurrence_split_child_resolves_through_parent(self):
        F.task(self.fk, "RP", owner="Administrator", assign=[F.GIVER], split=1, is_group=1)
        F.task(self.fk, "RC", owner="Administrator", assign=[F.ALICE], parent_task="RP", end="2026-10-16")
        self.fk.add("PM Recurrence", name="RULE2", owner=F.LEADER, last_task="RP")
        self.me()
        rows = self.q.list()["rows"]
        self.assertEqual([(r["name"], r["giver"]) for r in rows], [("RC", F.LEADER)])


class TestDigestText(Base):
    def _hook(self, sent):
        m = types.ModuleType("ecentric_workspace.notification_center.events")
        m.publish_notification_event = lambda et, u, title, msg, **k: sent.append((u, title, msg))
        sys.modules["ecentric_workspace.notification_center.events"] = m
        nc = sys.modules.get("ecentric_workspace.notification_center") or types.ModuleType("ecentric_workspace.notification_center")
        nc.events = m
        sys.modules["ecentric_workspace.notification_center"] = nc

    def test_only_asks_no_zero_headline(self):
        self.fk.module.get_conf = lambda: {"ec_pm_morning_digest": 1}
        F.task(self.fk, "REQ", owner=F.GIVER, assign=[], state="Backlog", subject="Setup kho")
        self.fk.add("PM Assignment Request", name="AR1", task="REQ", recipient=F.ALICE, requested_by=F.GIVER,
                    status="Pending", kind="Assignment")
        sent = []
        self._hook(sent)
        self.assertEqual(self.q.morning_digest(), {"sent": 1})
        u, title, msg = sent[0]
        self.assertEqual(u, F.ALICE)
        self.assertNotIn(" 0 việc", title)
        self.assertIn("1 việc chờ bạn nhận", title + " " + msg)

    def test_disabled_user_and_daily_dedupe_key(self):
        self.fk.module.get_conf = lambda: {"ec_pm_morning_digest": "1"}
        self.fk.row("User", F.BOB)["enabled"] = 0
        F.task(self.fk, "A1", assign=[F.ALICE], end="2026-10-15")
        F.task(self.fk, "B1", assign=[F.BOB], end="2026-10-15")
        sent, keys = [], []
        m = types.ModuleType("ecentric_workspace.notification_center.events")
        m.publish_notification_event = lambda et, u, title, msg, **k: (sent.append(u), keys.append(k.get("dedupe_key")))
        sys.modules["ecentric_workspace.notification_center.events"] = m
        nc = sys.modules.get("ecentric_workspace.notification_center") or types.ModuleType("ecentric_workspace.notification_center")
        nc.events = m
        sys.modules["ecentric_workspace.notification_center"] = nc
        self.q.morning_digest()
        self.q.morning_digest()   # cron chạy lại cùng ngày -> cùng khoá dedupe
        self.assertEqual(sent, [F.ALICE, F.ALICE])
        self.assertEqual(len(set(keys)), 1)


class TestStableOrder(Base):
    def test_ties_break_by_name_not_modified(self):
        F.task(self.fk, "TASK-0002", assign=[F.ALICE], end="2026-10-17", modified="2026-10-16 09:00:00")
        F.task(self.fk, "TASK-0001", assign=[F.ALICE], end="2026-10-17", modified="2026-10-16 09:30:00")
        self.me()
        self.assertEqual([r["name"] for r in self.q.list()["rows"]], ["TASK-0001", "TASK-0002"])
        self.fk.row("Task", "TASK-0001")["modified"] = "2026-10-01 00:00:00"
        self.assertEqual([r["name"] for r in self.q.list()["rows"]], ["TASK-0001", "TASK-0002"])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Hotfix 16 (PO 17/11/2026) - Việc cần làm backend.

  H1 "Tồn đọng" (stale) = trễ hơn 14 ngày: bucket riêng, xếp CUỐI, không vào số menu (main_count),
     không vào top 3 tin 8h30 (chỉ đếm). Trễ đúng 14 ngày vẫn là "Quá hạn".
  H2 Số menu "Việc cần làm" = hàng đợi chính (không tồn đọng) + việc "Cần đồng ý" chờ mình nhận.
  H3 Người giao là tài khoản hệ thống (Administrator) -> giver_system=1, tên "Hệ thống".
  H4 tab=follow: việc mình theo dõi (CC), cấp cao nhất, còn mở, cùng quy tắc xếp.
  H5 queue_actions.bulk: dời hạn / bỏ hạn chỉ cho việc mình giao (hoặc hệ thống giao); Xong đi
     tasks.mark_done (bị chặn thì báo); lỗi một việc không chặn việc khác; ngày quá khứ bị từ chối.
Fake 'now' = Fri 2026-10-16 10:00 (_pm_fake)."""
import os
import sys
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

    def names(self, out, key="rows"):
        return [r["name"] for r in out[key]]


# ------------------------------------------------------------------ H1 stale bucket
class TestStale(Base):
    def test_boundary_and_order(self):
        A = [F.ALICE]
        F.task(self.fk, "OLD15", assign=A, end="2026-10-01", priority="Urgent")    # 15 days late
        F.task(self.fk, "OLD14", assign=A, end="2026-10-02", priority="Low")       # 14 days late
        F.task(self.fk, "NODUE", assign=A)
        F.task(self.fk, "TODAY", assign=A, end="2026-10-16")
        self.me()
        out = self.q.list()
        self.assertEqual(self.names(out), ["OLD14", "TODAY", "NODUE", "OLD15"])
        b = {r["name"]: r["bucket"] for r in out["rows"]}
        self.assertEqual((b["OLD14"], b["OLD15"]), ("late", "stale"))
        self.assertEqual(out["counts"]["stale"], 1)
        self.assertEqual(out["buckets"][-1], {"key": "stale", "label": "Tồn đọng"})
        self.assertEqual(self.q.STALE_DAYS, 14)

    def test_main_count_leaves_stale_out(self):
        F.task(self.fk, "OLD", assign=[F.ALICE], end="2025-12-01")
        F.task(self.fk, "NOW", assign=[F.ALICE], end="2026-10-16")
        self.assertEqual(self.q.main_count(F.ALICE), 1)

    def test_digest_counts_stale_but_never_names_it(self):
        rows = self.q.ordered([
            {"name": "S1", "subject": "Ton dong 1", "exp_end_date": "2026-09-01", "priority": "Urgent"},
            {"name": "S2", "subject": "Ton dong 2", "exp_end_date": "2026-09-02"},
            {"name": "L1", "subject": "Tre 2 ngay", "exp_end_date": "2026-10-14"},
        ], "2026-10-16", "10:00")
        title, msg = self.q._digest_text(rows, [], "2026-10-16")
        self.assertEqual(title, "Hôm nay có 1 việc cần xử lý")
        self.assertIn("2 việc tồn đọng cần dọn", msg)
        self.assertIn("Tre 2 ngay", msg)
        self.assertNotIn("Ton dong", msg)


# ------------------------------------------------------------------ H2 badge = queue + asks
class TestBadge(Base):
    def test_badge_adds_requests_waiting_for_me(self):
        self.dash = self.fk.load("ecentric_workspace.pm.api.dashboard")
        F.task(self.fk, "NOW", assign=[F.ALICE], end="2026-10-16")
        F.task(self.fk, "OLD", assign=[F.ALICE], end="2026-09-01")
        F.task(self.fk, "ASKED", owner=F.GIVER, assign=[])
        self.fk.add("PM Assignment Request", name="REQ1", task="ASKED", requested_by=F.GIVER,
                    recipient=F.ALICE, status="Pending", kind="Assignment")
        self.me()
        self.assertEqual(self.dash.rail_badges()["mywork"], 2)   # NOW + REQ1 (OLD is stale)


# ------------------------------------------------------------------ H3 system giver
class TestSystemGiver(Base):
    def test_administrator_is_hethong(self):
        F.task(self.fk, "IMP", owner="Administrator", assign=[F.ALICE], end="2026-10-20")
        F.task(self.fk, "REAL", owner=F.GIVER, assign=[F.ALICE], end="2026-10-20")
        self.me()
        rows = {r["name"]: r for r in self.q.list()["rows"]}
        self.assertEqual((rows["IMP"]["giver_system"], rows["IMP"]["giver_name"]), (1, "Hệ thống"))
        self.assertEqual((rows["REAL"]["giver_system"], rows["REAL"]["giver_name"]), (0, "Gia Ver"))


# ------------------------------------------------------------------ H4 follow tab
class TestFollow(Base):
    def test_follow_tab_lists_open_top_level_followed(self):
        F.task(self.fk, "F1", owner=F.GIVER, assign=[F.BOB], end="2026-10-20")
        F.task(self.fk, "F2", owner=F.GIVER, assign=[F.BOB], end="2026-10-15", priority="High")
        F.task(self.fk, "FDONE", owner=F.GIVER, assign=[F.BOB], state="Done")
        F.task(self.fk, "FSUB", owner=F.GIVER, assign=[F.BOB], parent_task="F1")
        F.task(self.fk, "NOTF", owner=F.GIVER, assign=[F.BOB])
        for t in ("F1", "F2", "FDONE", "FSUB"):
            self.fk.add("PM Task Follower", name=t + "::" + F.ALICE, task=t, user=F.ALICE, source="manual")
        self.me()
        out = self.q.list(tab="follow")
        self.assertEqual(out["tab"], "follow")
        self.assertEqual(self.names(out), ["F2", "F1"])
        f2 = out["rows"][0]
        self.assertEqual(f2["giver_name"], "Gia Ver")
        self.assertEqual([a["name"] for a in f2["assignees"]], ["Bob"])

    def test_unknown_tab_is_me(self):
        self.me()
        self.assertEqual(self.q.list(tab="weird")["tab"], "me")


# ------------------------------------------------------------------ H5 bulk
class TestBulk(Base):
    def setUp(self):
        super().setUp()
        self.qa = self.fk.load("ecentric_workspace.pm.api.queue_actions")
        F.task(self.fk, "MINE", owner=F.ALICE, assign=[F.ALICE], end="2026-09-01", pm_end_time="9:00:00")
        F.task(self.fk, "SYS", owner="Administrator", assign=[F.ALICE], end="2026-09-01")
        F.task(self.fk, "THEIRS", owner=F.GIVER, assign=[F.ALICE], end="2026-09-01")
        self.me()

    def test_move_only_mine_and_system(self):
        out = self.qa.bulk("move", '["MINE", "SYS", "THEIRS", "GHOST"]', due="2026-10-20")
        self.assertEqual(sorted(out["ok"]), ["MINE", "SYS"])
        self.assertEqual({s["name"]: s["reason"] for s in out["skipped"]}, {"THEIRS": "others", "GHOST": "not_found"})
        self.assertEqual(str(self.fk.row("Task", "MINE")["exp_end_date"])[:10], "2026-10-20")
        self.assertEqual(str(self.fk.row("Task", "THEIRS")["exp_end_date"])[:10], "2026-09-01")

    def test_clear_removes_date_and_time(self):
        out = self.qa.bulk("clear", ["MINE"])
        self.assertEqual(out["ok"], ["MINE"])
        r = self.fk.row("Task", "MINE")
        self.assertFalse(r.get("exp_end_date"))
        self.assertFalse(r.get("pm_end_time"))

    def test_done_goes_through_mark_done_for_every_task(self):
        out = self.qa.bulk("done", ["MINE", "THEIRS"])
        self.assertEqual(sorted(out["ok"]), ["MINE", "THEIRS"])
        self.assertEqual(self.fk.row("Task", "MINE")["workflow_state"], "Done")

    def test_past_date_and_bad_action_rejected(self):
        with self.assertRaises(Exception):
            self.qa.bulk("move", ["MINE"], due="2026-10-15")
        with self.assertRaises(Exception):
            self.qa.bulk("delete", ["MINE"])
        with self.assertRaises(Exception):
            self.qa.bulk("done", [])

    def test_one_failure_is_rolled_back_and_reported(self):
        import ecentric_workspace.pm.api.tasks as tasks
        orig = tasks.mark_done

        def boom(name):
            if name == "MINE":
                raise Exception("hong")
            return orig(name)
        tasks.mark_done = boom
        try:
            out = self.qa.bulk("done", ["MINE", "THEIRS"])
        finally:
            tasks.mark_done = orig
        self.assertEqual(out["ok"], ["THEIRS"])
        self.assertEqual(out["skipped"][0]["reason"], "error")
        self.assertIn("pmq_bulk_0", self.fk.db.rolled_back)

    def test_outsider_cannot_touch(self):
        self.me(F.OUTSIDER)
        out = self.qa.bulk("done", ["MINE"])
        self.assertEqual(out["ok"], [])
        self.assertEqual(out["skipped"][0]["reason"], "not_found")   # QC: never reveal someone else's task
        self.assertEqual(self.fk.row("Task", "MINE")["workflow_state"], "To Do")


if __name__ == "__main__":
    unittest.main()

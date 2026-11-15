# -*- coding: utf-8 -*-
"""QC round 2 (15/11/2026) - Việc cần làm backend.

Phần A (điểm round 1 để lại, mặc định PO-friendly):
  A1 Việc mình đã gửi kiểm tra, chờ NGƯỜI KHÁC duyệt -> `waiting` (không vào rows/counts/top 3/08:30);
     Review mà mình là người giao -> vẫn ở hàng đợi chính.
  A2 Việc cha "mỗi người một việc" của mình -> tab giao, tiến độ x/y; chỉ vào hàng đợi chính khi Review.
  A3 Nhận việc qua Cần đồng ý -> ghi "đã mở" (PM Task Seen) -> người giao hết thấy "Chưa mở việc".
  A4 Tab giao: việc chờ người nhận đồng ý (Pending, requested_by = mình) + việc sinh từ quy tắc lặp của mình.
  A5 Giới hạn 500: hạn gần nhất trước (việc quá hạn cũ không rơi), cờ `truncated`.
Phần B (dữ liệu bẩn / thời gian / số truy vấn).
Fake 'now' = Fri 2026-10-16 10:00 (_pm_fake)."""
import datetime
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

    def names(self, out, key="rows"):
        return [r["name"] for r in out[key]]

    def hook_digest(self, sent):
        m = types.ModuleType("ecentric_workspace.notification_center.events")
        m.publish_notification_event = lambda et, u, title, msg, **k: sent.append((u, title, msg))
        sys.modules["ecentric_workspace.notification_center.events"] = m
        nc = sys.modules.get("ecentric_workspace.notification_center") or types.ModuleType("ecentric_workspace.notification_center")
        nc.events = m
        sys.modules["ecentric_workspace.notification_center"] = nc


# ------------------------------------------------------------------ A1
class TestWaitingForReview(Base):
    def seed(self):
        F.task(self.fk, "SENT", owner=F.GIVER, assign=[F.ALICE], state="Review", end="2026-10-15", review=1)
        F.task(self.fk, "SELF_RV", owner=F.ALICE, assign=[F.ALICE], state="Review", end="2026-10-17")
        F.task(self.fk, "WORK", owner=F.GIVER, assign=[F.ALICE], end="2026-10-16")

    def test_waiting_not_in_rows_counts_rank(self):
        self.seed()
        self.me()
        out = self.q.list()
        self.assertEqual(self.names(out), ["WORK", "SELF_RV"])
        self.assertEqual([r["rank"] for r in out["rows"]], [1, 2])
        self.assertEqual(self.names(out, "waiting"), ["SENT"])
        w = out["waiting"][0]
        self.assertEqual((w["waiting"], w["rank"], w["bucket"], w["giver"]), (1, 0, "late", F.GIVER))
        self.assertEqual(out["counts"]["late"], 0)          # SENT is late but waits for GIVER
        self.assertEqual(sum(out["counts"].values()), 2)

    def test_review_i_must_approve_stays_main(self):
        self.seed()
        self.me()
        rows = {r["name"]: r for r in self.q.list()["rows"]}
        self.assertTrue(rows["SELF_RV"]["self"])
        self.assertNotIn("waiting", rows["SELF_RV"])

    def test_waiting_only_late_task_sends_no_digest(self):
        self.fk.module.get_conf = lambda: {"ec_pm_morning_digest": 1}
        F.task(self.fk, "SENT", owner=F.GIVER, assign=[F.ALICE], state="Review", end="2026-10-15")
        sent = []
        self.hook_digest(sent)
        self.assertEqual(self.q.morning_digest(), {"sent": 0})

    def test_digest_top3_skips_waiting(self):
        self.fk.module.get_conf = lambda: {"ec_pm_morning_digest": 1}
        F.task(self.fk, "SENT", owner=F.GIVER, assign=[F.ALICE], state="Review", end="2026-10-01",
               priority="Urgent", subject="Da gui kiem tra")
        F.task(self.fk, "A1", owner=F.GIVER, assign=[F.ALICE], end="2026-10-16", subject="Chot GMV")
        sent = []
        self.hook_digest(sent)
        self.q.morning_digest()
        u, title, msg = sent[0]
        self.assertIn("1 việc", title)
        self.assertIn("1. Chot GMV", msg)
        self.assertNotIn("Da gui kiem tra", msg)

    def test_waiting_empty_list_on_give_tab(self):
        self.seed()
        self.me()
        self.assertEqual(self.q.list(tab="give")["waiting"], [])


# ------------------------------------------------------------------ A2
class TestSplitParent(Base):
    def seed(self, state="In Progress"):
        F.task(self.fk, "SP", owner=F.ALICE, assign=[F.ALICE], split=1, is_group=1, state=state, end="2026-10-20")
        F.task(self.fk, "SP-B", owner=F.ALICE, assign=[F.BOB], parent_task="SP", state="Done", end="2026-10-20")
        F.task(self.fk, "SP-G", owner=F.ALICE, assign=[F.GIVER], parent_task="SP", end="2026-10-20")
        F.task(self.fk, "SP-X", owner=F.ALICE, assign=[F.LEADER], parent_task="SP", state="Cancelled")

    def test_not_in_my_queue_but_in_given_with_progress(self):
        self.seed()
        self.me()
        self.assertEqual(self.names(self.q.list()), [])
        out = self.q.list(tab="give")
        self.assertEqual(self.names(out), ["SP"])           # children folded into the parent
        sp = out["rows"][0]
        self.assertEqual(sp["progress"], {"done": 1, "total": 2})
        self.assertEqual(sp["group"], 1)
        self.assertEqual(sorted(a["user"] for a in sp["assignees"]), [F.BOB, F.GIVER])

    def test_review_parent_joins_main_queue(self):
        self.seed(state="Review")
        self.me()
        rows = self.q.list()["rows"]
        self.assertEqual([(r["name"], r["self"]) for r in rows], [("SP", True)])

    def test_child_in_review_stays_visible_on_give(self):
        self.seed()
        self.fk.row("Task", "SP-G")["workflow_state"] = "Review"
        self.me()
        self.assertEqual(sorted(self.names(self.q.list(tab="give"))), ["SP", "SP-G"])

    def test_someone_elses_split_parent_untouched(self):
        # GIVER's split parent assigned (oddly) to ALICE: not hers to give -> stays in her queue
        F.task(self.fk, "OSP", owner=F.GIVER, assign=[F.ALICE], split=1, is_group=1, end="2026-10-20")
        self.me()
        self.assertEqual(self.names(self.q.list()), ["OSP"])
        self.assertEqual(self.names(self.q.list(tab="give")), [])

    def test_split_opened_flag_reads_the_child(self):
        self.seed()
        self.fk.add("PM Task Seen", name="SP-G::" + F.GIVER, task="SP-G", user=F.GIVER)
        self.me()
        sp = self.q.list(tab="give")["rows"][0]
        self.assertFalse(sp["unopened"])
        self.assertTrue(all(a["opened"] for a in sp["assignees"]))


# ------------------------------------------------------------------ A3
class TestAcceptMarksOpened(Base):
    def test_accept_records_seen_and_clears_unopened(self):
        asg = self.fk.load("ecentric_workspace.pm.api.assignment")
        self.fk.load("ecentric_workspace.pm.api.tasks")
        self.fk.hooks["PM Assignment Request"] = [asg.pm_assignment_request_guard]
        F.task(self.fk, "REQ", owner=F.ALICE, assign=[], state="To Do")
        self.fk.add("PM Assignment Request", name="AR1", task="REQ", recipient=F.BOB, requested_by=F.ALICE,
                    status="Pending", kind="Assignment", open_task_key="REQ", open_request_key="REQ::" + F.BOB)
        self.me()
        row = self.q.list(tab="give")["rows"][0]
        self.assertEqual((row["name"], row["awaiting"], row["unopened"]), ("REQ", 1, False))
        self.me(F.BOB)
        asg.respond("AR1", "accept")
        self.assertTrue(self.fk.row("PM Task Seen", "REQ::" + F.BOB))
        self.me()
        row = self.q.list(tab="give")["rows"][0]
        self.assertEqual((row["awaiting"], row["unopened"]), (0, False))
        self.assertEqual(row["assignees"][0]["user"], F.BOB)

    def test_reject_does_not_mark_opened(self):
        asg = self.fk.load("ecentric_workspace.pm.api.assignment")
        self.fk.load("ecentric_workspace.pm.api.tasks")
        self.fk.hooks["PM Assignment Request"] = [asg.pm_assignment_request_guard]
        F.task(self.fk, "REQ", owner=F.ALICE, assign=[], state="To Do")
        self.fk.add("PM Assignment Request", name="AR1", task="REQ", recipient=F.BOB, requested_by=F.ALICE,
                    status="Pending", kind="Assignment", open_task_key="REQ", open_request_key="REQ::" + F.BOB)
        self.me(F.BOB)
        asg.respond("AR1", "reject", reason="ban")
        self.assertIsNone(self.fk.row("PM Task Seen", "REQ::" + F.BOB))


# ------------------------------------------------------------------ A4
class TestGivenAdditions(Base):
    def test_pending_request_shows_awaiting_once(self):
        F.task(self.fk, "ASK", owner=F.ALICE, assign=[], state="Backlog", end="2026-10-20")
        self.fk.add("PM Assignment Request", name="R1", task="ASK", recipient=F.BOB, requested_by=F.ALICE,
                    status="Pending", kind="Assignment")
        # deadline request I sent as assignee -> not "việc tôi giao"
        F.task(self.fk, "THEIRS", owner=F.GIVER, assign=[F.ALICE], end="2026-10-20")
        self.fk.add("PM Assignment Request", name="R2", task="THEIRS", recipient=F.GIVER, requested_by=F.ALICE,
                    status="Pending", kind="Deadline")
        # someone else's pending request -> never shown to me
        F.task(self.fk, "BOBS", owner=F.BOB, assign=[], state="Backlog")
        self.fk.add("PM Assignment Request", name="R3", task="BOBS", recipient=F.GIVER, requested_by=F.BOB,
                    status="Pending", kind="Assignment")
        self.me()
        out = self.q.list(tab="give")
        self.assertEqual(self.names(out), ["ASK"])
        r = out["rows"][0]
        self.assertEqual((r["awaiting"], r["assignees"][0]["user"], r["assignees"][0]["pending"]), (1, F.BOB, 1))
        self.assertFalse(r["unopened"])

    def test_pending_request_on_task_already_listed_no_duplicate(self):
        F.task(self.fk, "BOTH", owner=F.ALICE, assign=[F.GIVER], end="2026-10-20")
        self.fk.add("PM Assignment Request", name="R1", task="BOTH", recipient=F.BOB, requested_by=F.ALICE,
                    status="Pending", kind="Assignment")
        self.me()
        self.assertEqual(self.names(self.q.list(tab="give")), ["BOTH"])

    def test_pending_split_part_folded_into_parent(self):
        F.task(self.fk, "SP", owner=F.ALICE, assign=[F.ALICE], split=1, is_group=1, end="2026-10-20")
        F.task(self.fk, "SP-1", owner=F.ALICE, assign=[], parent_task="SP", end="2026-10-20")
        self.fk.add("PM Assignment Request", name="R1", task="SP-1", recipient=F.BOB, requested_by=F.ALICE,
                    status="Pending", kind="Assignment")
        self.me()
        out = self.q.list(tab="give")
        self.assertEqual(self.names(out), ["SP"])
        a = out["rows"][0]["assignees"]
        self.assertEqual([(x["user"], x["pending"]) for x in a], [(F.BOB, 1)])

    def test_recurrence_occurrence_of_my_rule(self):
        F.task(self.fk, "OCC", owner="Administrator", assign=[F.BOB], end="2026-10-19")
        self.fk.add("PM Recurrence", name="RULE1", owner=F.ALICE, last_task="OCC")
        F.task(self.fk, "OCC2", owner="Administrator", assign=[F.BOB], end="2026-10-19")
        self.fk.add("PM Recurrence", name="RULE2", owner=F.GIVER, last_task="OCC2")
        self.me()
        out = self.q.list(tab="give")
        self.assertEqual(self.names(out), ["OCC"])
        self.assertEqual(out["rows"][0]["giver"], F.ALICE)
        self.me(F.GIVER)
        self.assertEqual(self.names(self.q.list(tab="give")), ["OCC2"])

    def test_recurring_split_parent_children_folded(self):
        F.task(self.fk, "RP", owner="Administrator", assign=[F.ALICE], split=1, is_group=1, end="2026-10-19")
        F.task(self.fk, "RC", owner="Administrator", assign=[F.BOB], parent_task="RP", end="2026-10-19")
        self.fk.add("PM Recurrence", name="RULE1", owner=F.ALICE, last_task="RP")
        self.me()
        out = self.q.list(tab="give")
        self.assertEqual(self.names(out), ["RP"])
        self.assertEqual(out["rows"][0]["progress"], {"done": 0, "total": 1})
        self.assertEqual(self.names(self.q.list()), [])     # split parent of my rule: not in my queue


# ------------------------------------------------------------------ A5
class TestLimit(Base):
    def test_old_overdue_never_cut_and_truncated_flag(self):
        for i in range(520):
            F.task(self.fk, "A%03d" % i, assign=[F.ALICE])                     # no due date
        F.task(self.fk, "ZZZ_OLD", assign=[F.ALICE], end="2025-01-02")       # sorts last by name
        self.me()
        out = self.q.list()
        self.assertEqual(len(out["rows"]), 500)
        self.assertEqual(out["truncated"], 1)
        self.assertEqual(out["rows"][0]["name"], "ZZZ_OLD")
        self.assertEqual(out["rows"][0]["bucket"], "late")

    def test_not_truncated_under_limit(self):
        F.task(self.fk, "T1", assign=[F.ALICE], end="2026-10-20")
        self.me()
        self.assertEqual(self.q.list()["truncated"], 0)

    def test_give_tab_query_count_500(self):
        for i in range(500):
            F.task(self.fk, "G%03d" % i, owner=F.ALICE, assign=[F.BOB], end="2026-10-%02d" % (10 + i % 15))
        calls = {"get_all": 0, "get_value": 0}
        ga, gv = self.fk.module.get_all, self.fk.db.get_value

        def cga(*a, **k):
            calls["get_all"] += 1
            return ga(*a, **k)

        def cgv(*a, **k):
            calls["get_value"] += 1
            return gv(*a, **k)
        self.fk.module.get_all, self.fk.db.get_value = cga, cgv
        self.me()
        out = self.q.list(tab="give")
        self.assertEqual(len(out["rows"]), 500)
        self.assertLessEqual(calls["get_all"], 15, calls)
        self.assertLessEqual(calls["get_value"], 3, calls)


# ------------------------------------------------------------------ B dirty data
class TestDirtyData(Base):
    def test_dirty_rows_never_break_the_queue(self):
        F.task(self.fk, "NOSUBJ", assign=[F.ALICE], subject=None, end="2026-10-16")
        F.task(self.fk, "PRI_EMPTY", assign=[F.ALICE], priority="", end="2026-10-16")
        F.task(self.fk, "PRI_ODD", assign=[F.ALICE], priority="Siêu gấp", end="2026-10-16")
        F.task(self.fk, "BADDATE", assign=[F.ALICE], end="16/10/2026")
        F.task(self.fk, "BADDATE2", assign=[F.ALICE], end="2026-02-30")
        F.task(self.fk, "T95", assign=[F.ALICE], end="2026-10-16", pm_end_time="9:5:0")
        F.task(self.fk, "TDELTA", assign=[F.ALICE], end="2026-10-16", pm_end_time=datetime.timedelta(hours=17, minutes=30))
        F.task(self.fk, "T25", assign=[F.ALICE], end="2026-10-16", pm_end_time="25:00:00")
        F.task(self.fk, "NODATE_TIME", assign=[F.ALICE], pm_end_time="9:00:00")
        F.task(self.fk, "GONEPROJ", assign=[F.ALICE], project="DELETED", end="2026-10-17")
        F.task(self.fk, "BROKEN_JSON", assign=None, end="2026-10-16")
        self.fk.row("Task", "BROKEN_JSON")["_assign"] = '["alice@ec.vn"'
        F.task(self.fk, "BARE_STR", assign=None, end="2026-10-16")
        self.fk.row("Task", "BARE_STR")["_assign"] = '"alice@ec.vn"'
        self.me()
        out = self.q.list()
        rows = {r["name"]: r for r in out["rows"]}
        self.assertNotIn("BROKEN_JSON", rows)
        self.assertNotIn("BARE_STR", rows)
        self.assertEqual(rows["NOSUBJ"]["subject"], None)            # FE shows the task code
        self.assertEqual((rows["PRI_EMPTY"]["priority_rank"], rows["PRI_ODD"]["priority_rank"]), (2, 2))
        self.assertEqual((rows["BADDATE"]["bucket"], rows["BADDATE"]["due"]), ("none", None))
        self.assertEqual(rows["BADDATE2"]["bucket"], "none")
        self.assertEqual((rows["T95"]["due_time"], rows["T95"]["bucket"]), ("09:05", "late"))
        self.assertEqual((rows["TDELTA"]["due_time"], rows["TDELTA"]["bucket"]), ("17:30", "today"))
        self.assertEqual(rows["T25"]["due_time"], None)
        self.assertEqual((rows["NODATE_TIME"]["due"], rows["NODATE_TIME"]["due_time"]), (None, None))
        self.assertEqual(rows["GONEPROJ"]["project_name"], "")

    def test_assignees_of_bare_string_is_empty(self):
        perm = self.fk.load("ecentric_workspace.pm.permissions")
        self.assertEqual(perm.assignees_of({"_assign": '"alice@ec.vn"'}), [])
        self.assertEqual(perm.assignees_of({"_assign": '{"a": 1}'}), [])
        self.assertEqual(perm.assignees_of({"_assign": '["a@x.vn", 5, null]'}), ["a@x.vn"])

    def test_left_people_flagged(self):
        self.fk.row("User", F.GIVER)["enabled"] = 0
        self.fk.row("User", F.BOB)["enabled"] = 0
        F.task(self.fk, "FROM_LEFT", owner=F.GIVER, assign=[F.ALICE], end="2026-10-17")
        F.task(self.fk, "TO_LEFT", owner=F.ALICE, assign=[F.BOB], end="2026-10-17")
        self.me()
        self.assertEqual(self.q.list()["rows"][0]["giver_left"], 1)
        g = self.q.list(tab="give")["rows"][0]
        self.assertEqual(g["assignees"][0]["left"], 1)

    def test_nested_parent_child_both_mine(self):
        F.task(self.fk, "PARENT", owner=F.GIVER, assign=[F.ALICE], is_group=1, end="2026-10-18")
        F.task(self.fk, "CHILD", owner=F.GIVER, assign=[F.ALICE], parent_task="PARENT", end="2026-10-17")
        F.task(self.fk, "GRAND", owner=F.GIVER, assign=[F.ALICE], parent_task="CHILD", end="2026-10-16")
        self.me()
        self.assertEqual(self.names(self.q.list()), ["GRAND", "CHILD", "PARENT"])


# ------------------------------------------------------------------ B time
class TestTimeEdges(Base):
    def test_pure_buckets_at_edges(self):
        b = self.q.bucket
        self.assertEqual(b({"exp_end_date": "2026-10-16", "pm_end_time": "0:30:00"}, "2026-10-16", "00:00"), "today")
        self.assertEqual(b({"exp_end_date": "2026-10-15"}, "2026-10-16", "00:00"), "late")
        self.assertEqual(b({"exp_end_date": "2026-10-16", "pm_end_time": "23:59:00"}, "2026-10-16", "23:59"), "today")
        self.assertEqual(b({"exp_end_date": "2026-10-16", "pm_end_time": "23:58:00"}, "2026-10-16", "23:59"), "late")
        # Sunday: tomorrow is Monday; "Còn lại tuần này" cannot hold anything
        self.assertEqual(b({"exp_end_date": "2026-10-19"}, "2026-10-18", "10:00"), "tomorrow")
        self.assertEqual(b({"exp_end_date": "2026-10-20"}, "2026-10-18", "10:00"), "later")
        # Saturday: Sunday = tomorrow, Monday = next week
        self.assertEqual(b({"exp_end_date": "2026-10-19"}, "2026-10-17", "10:00"), "later")
        # month / year end
        self.assertEqual(b({"exp_end_date": "2026-11-01"}, "2026-10-31", "10:00"), "tomorrow")
        self.assertEqual(b({"exp_end_date": "2027-01-01"}, "2026-12-31", "10:00"), "tomorrow")
        self.assertEqual(b({"exp_end_date": "2027-01-03"}, "2026-12-31", "10:00"), "week")
        self.assertEqual(b({"exp_end_date": "2027-01-04"}, "2026-12-31", "10:00"), "later")

    def test_sunday_list_has_no_week_bucket(self):
        F.task(self.fk, "MON", assign=[F.ALICE], end="2026-10-19")
        F.task(self.fk, "TUE", assign=[F.ALICE], end="2026-10-20")
        self.fk.advance(days=2)                 # Sun 2026-10-18 10:00
        self.me()
        out = self.q.list()
        self.assertEqual((out["today"], out["counts"]["week"]), ("2026-10-18", 0))
        self.assertEqual([r["bucket"] for r in out["rows"]], ["tomorrow", "later"])

    def test_server_clock_is_returned(self):
        self.fk.advance(hours=13, minutes=59)   # 23:59
        self.me()
        out = self.q.list()
        self.assertEqual((out["today"], out["now"]), ("2026-10-16", "23:59"))


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""QC round 3 (15/11/2026) - Việc cần làm backend.

  C1 Số "Việc cần làm" trên menu trái (dashboard.rail_badges.mywork) = đúng số dòng hàng đợi chính của
     queue.list(tab=me): không đếm việc chờ người khác duyệt, việc cha "mỗi người một việc" của mình,
     việc nhật ký cá nhân. Một quy tắc (queue._me_rows), không truy vấn theo từng dòng.
  C2 Tab "Việc tôi giao": người nhận "Đề xuất hạn khác" (PM Assignment Request Reschedule Proposed,
     requested_by = mình, kind != Deadline) -> `proposals` (riêng, trên đầu, không vào rows/counts),
     kèm hạn đề xuất + lý do; Đồng ý hạn mới (accept_counter) -> thành việc đã giao; Giữ hạn cũ, gửi lại
     (resend) -> "Chờ nhận".
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
        self.dash = self.fk.load("ecentric_workspace.pm.api.dashboard")

    def me(self, u=F.ALICE):
        self.fk.set_user(u)

    def names(self, out, key="rows"):
        return [r["name"] for r in out[key]]


# ------------------------------------------------------------------ C1 badge = main queue
class TestBadgeMatchesQueue(Base):
    def seed(self):
        F.task(self.fk, "WORK", owner=F.GIVER, assign=[F.ALICE], end="2026-10-16")
        F.task(self.fk, "SELF", owner=F.ALICE, assign=[F.ALICE])
        F.task(self.fk, "SELF_RV", owner=F.ALICE, assign=[F.ALICE], state="Review")       # I approve it
        F.task(self.fk, "SENT", owner=F.GIVER, assign=[F.ALICE], state="Review", end="2026-10-01")  # waits for GIVER
        F.task(self.fk, "SP", owner=F.ALICE, assign=[F.ALICE], split=1, is_group=1, end="2026-10-20")
        F.task(self.fk, "SP-B", owner=F.ALICE, assign=[F.BOB], parent_task="SP", end="2026-10-20")
        self.fk.add("Project", name="WL", project_name="Nhat ky", ec_personal_log=1)
        F.task(self.fk, "LOG", owner=F.ALICE, assign=[F.ALICE], project="WL", end="2026-10-16")
        F.task(self.fk, "DONE", owner=F.GIVER, assign=[F.ALICE], state="Done")
        F.task(self.fk, "CXL", owner=F.GIVER, assign=[F.ALICE], state="Cancelled")
        F.task(self.fk, "SUBSTR", owner=F.GIVER, assign=["xalice@ec.vn"])                 # not mine
        F.task(self.fk, "BOBS", owner=F.ALICE, assign=[F.BOB])                              # I gave it

    def test_badge_equals_rows_of_tab_me(self):
        self.seed()
        self.me()
        rows = self.names(self.q.list())
        self.assertEqual(sorted(rows), ["SELF", "SELF_RV", "WORK"])
        self.assertEqual(self.dash.rail_badges()["mywork"], len(rows))
        self.assertEqual(self.q.main_count(F.ALICE), 3)

    def test_badge_follows_the_queue_after_changes(self):
        self.seed()
        self.me()
        self.fk.row("Task", "SP")["workflow_state"] = "Review"        # split parent waiting for MY approval
        self.fk.row("Task", "SENT")["workflow_state"] = "In Progress"  # returned to me
        self.assertEqual(self.dash.rail_badges()["mywork"], len(self.q.list()["rows"]))
        self.assertEqual(self.dash.rail_badges()["mywork"], 5)

    def test_badge_zero_when_only_waiting(self):
        F.task(self.fk, "SENT", owner=F.GIVER, assign=[F.ALICE], state="Review", end="2026-10-01")
        self.me()
        self.assertEqual(self.dash.rail_badges()["mywork"], 0)
        self.assertEqual(self.names(self.q.list(), "waiting"), ["SENT"])

    def test_badge_contract_and_silent_for_non_pm(self):
        self.seed()
        self.me()
        self.assertEqual(sorted(self.dash.rail_badges()), ["assignments", "mywork", "received"])
        self.me("nopm@ec.vn")
        self.assertEqual(self.dash.rail_badges(), {"mywork": 0, "assignments": 0, "received": 0})

    def test_badge_never_throws_when_queue_breaks(self):
        self.seed()
        self.me()
        import ecentric_workspace.pm.api.queue as realq
        orig = realq.main_count
        realq.main_count = lambda u: 1 / 0
        try:
            b = self.dash.rail_badges()
        finally:
            realq.main_count = orig
        self.assertEqual(b["mywork"], 0)
        self.assertIn("received", b)

    def _badge_calls(self):
        calls = {"get_all": 0, "get_value": 0}
        ga, gv = self.fk.module.get_all, self.fk.db.get_value

        def cga(*a, **k):
            calls["get_all"] += 1
            return ga(*a, **k)

        def cgv(*a, **k):
            calls["get_value"] += 1
            return gv(*a, **k)
        self.fk.module.get_all, self.fk.db.get_value = cga, cgv
        try:
            n = self.dash.rail_badges()["mywork"]
        finally:
            self.fk.module.get_all, self.fk.db.get_value = ga, gv
        return n, calls

    def test_badge_no_per_row_queries(self):
        def seed(lo, hi):
            for i in range(lo, hi):
                owner = "Administrator" if i % 3 == 0 else F.GIVER       # recurrence-style system owner
                F.task(self.fk, "T%03d" % i, owner=owner, assign=[F.ALICE], end="2026-10-%02d" % (10 + i % 15),
                       state="Review" if i % 5 == 0 else "To Do")
        self.me()
        seed(0, 6)
        _n, small = self._badge_calls()
        seed(6, 300)
        n, big = self._badge_calls()
        self.assertEqual(big, small)                       # same number of queries for 6 or 300 tasks
        self.assertLessEqual(big["get_all"], 16, big)      # whole badge request (mywork + received)
        self.assertEqual(n, len(self.q.list()["rows"]))


# ------------------------------------------------------------------ C2 proposals on tab give
class TestCounterProposals(Base):
    def req(self, name, task, recipient=F.BOB, by=F.ALICE, status="Reschedule Proposed", kind="Assignment", **kw):
        row = dict(name=name, task=task, recipient=recipient, requested_by=by, status=status, kind=kind,
                   proposed_end=kw.pop("proposed_end", "2026-10-17 18:00:00"),
                   counter_end=kw.pop("counter_end", "2026-10-22 17:30:00"),
                   counter_start=kw.pop("counter_start", None),
                   response_reason=kw.pop("reason", "Dang ban viec khac"))
        row.update(kw)
        if status in ("Pending", "Reschedule Proposed"):
            row.setdefault("open_task_key", task)
            row.setdefault("open_request_key", task + "::" + recipient)
        return self.fk.add("PM Assignment Request", **row)

    def test_proposal_listed_separately_with_counter(self):
        F.task(self.fk, "ASK", owner=F.ALICE, assign=[], state="Backlog", end="2026-10-17")
        self.req("AR1", "ASK")
        F.task(self.fk, "GAVE", owner=F.ALICE, assign=[F.BOB], end="2026-10-20")
        self.me()
        out = self.q.list(tab="give")
        self.assertEqual(self.names(out), ["GAVE"])                      # not in rows
        self.assertEqual(sum(out["counts"].values()), 1)                 # not counted
        self.assertEqual(self.names(out, "proposals"), ["ASK"])
        p = out["proposals"][0]
        c = p["counter"]
        self.assertEqual((c["request"], c["recipient"], c["recipient_name"]), ("AR1", F.BOB, "Bob"))
        self.assertEqual((c["due"], c["time"], c["old_due"], c["old_time"]), ("2026-10-22", "17:30", "2026-10-17", "18:00"))
        self.assertEqual(c["reason"], "Dang ban viec khac")
        self.assertEqual((p["rank"], p["awaiting"]), (0, 0))
        self.assertEqual(p["assignees"][0]["user"], F.BOB)
        self.assertNotIn("_people", p)

    def test_tab_me_has_no_proposals(self):
        F.task(self.fk, "ASK", owner=F.ALICE, assign=[], state="Backlog")
        self.req("AR1", "ASK")
        self.me()
        self.assertEqual(self.q.list()["proposals"], [])

    def test_only_my_open_assignment_proposals(self):
        F.task(self.fk, "DL", owner=F.GIVER, assign=[F.ALICE], end="2026-10-20")
        self.req("R1", "DL", recipient=F.GIVER, kind="Deadline")                     # deadline kind
        F.task(self.fk, "BOBS", owner=F.BOB, assign=[], state="Backlog")
        self.req("R2", "BOBS", recipient=F.GIVER, by=F.BOB)                         # someone else's
        F.task(self.fk, "OLD", owner=F.ALICE, assign=[], state="Cancelled")
        self.req("R3", "OLD")                                                        # task closed
        F.task(self.fk, "PEND", owner=F.ALICE, assign=[], state="Backlog")
        self.req("R4", "PEND", status="Pending")                                     # still awaiting
        self.me()
        out = self.q.list(tab="give")
        self.assertEqual(out["proposals"], [])
        self.assertEqual(self.names(out), ["PEND"])
        self.assertEqual(out["rows"][0]["awaiting"], 1)

    def test_task_not_owned_by_me_still_listed(self):
        # request on GIVER's task that I (ALICE) sent - requested_by = me decides, not owner
        F.task(self.fk, "XT", owner=F.GIVER, assign=[], state="Backlog")
        self.req("R1", "XT")
        self.me()
        self.assertEqual(self.names(self.q.list(tab="give"), "proposals"), ["XT"])

    def test_split_child_folded_and_listed(self):
        F.task(self.fk, "SP", owner=F.ALICE, assign=[F.ALICE], split=1, is_group=1, end="2026-10-20")
        F.task(self.fk, "SP-B", owner=F.ALICE, assign=[], parent_task="SP", state="Backlog", end="2026-10-20")
        F.task(self.fk, "SP-G", owner=F.ALICE, assign=[F.GIVER], parent_task="SP", end="2026-10-20")
        self.req("R1", "SP-B")
        self.me()
        out = self.q.list(tab="give")
        self.assertEqual(self.names(out), ["SP"])
        sp = out["rows"][0]
        self.assertEqual(sp["progress"], {"done": 0, "total": 2})
        self.assertEqual(sorted(a["user"] for a in sp["assignees"]), [F.BOB, F.GIVER])
        self.assertEqual(self.names(out, "proposals"), ["SP-B"])

    def test_personal_log_proposal_hidden_by_default(self):
        self.fk.add("Project", name="WL", project_name="Nhat ky", ec_personal_log=1)
        F.task(self.fk, "ASK", owner=F.ALICE, assign=[], state="Backlog", project="WL")
        self.req("AR1", "ASK")
        self.me()
        self.assertEqual(self.q.list(tab="give")["proposals"], [])
        self.assertEqual(self.names(self.q.list(tab="give", include_personal=1), "proposals"), ["ASK"])

    def test_counter_without_end_keeps_start(self):
        F.task(self.fk, "ASK", owner=F.ALICE, assign=[], state="Backlog")
        self.req("AR1", "ASK", counter_end=None, counter_start="2026-10-19 00:00:00", proposed_end=None)
        self.me()
        c = self.q.list(tab="give")["proposals"][0]["counter"]
        self.assertEqual((c["due"], c["time"], c["start"], c["old_due"]), (None, None, "2026-10-19", None))

    def _actions(self):
        asg = self.fk.load("ecentric_workspace.pm.api.assignment")
        self.fk.load("ecentric_workspace.pm.api.tasks")
        self.fk.hooks["PM Assignment Request"] = [asg.pm_assignment_request_guard]
        return asg

    def test_accept_counter_moves_to_given_rows(self):
        asg = self._actions()
        F.task(self.fk, "ASK", owner=F.ALICE, assign=[], state="To Do", end="2026-10-17")
        self.req("AR1", "ASK")
        self.me()
        asg.requester_action("AR1", "accept_counter")
        out = self.q.list(tab="give")
        self.assertEqual(out["proposals"], [])
        self.assertEqual(self.names(out), ["ASK"])
        self.assertEqual(out["rows"][0]["due"], "2026-10-22")
        self.assertEqual(out["rows"][0]["assignees"][0]["user"], F.BOB)

    def test_resend_moves_back_to_awaiting(self):
        asg = self._actions()
        F.task(self.fk, "ASK", owner=F.ALICE, assign=[], state="Backlog", end="2026-10-17")
        self.req("AR1", "ASK")
        self.me()
        asg.requester_action("AR1", "resend")
        out = self.q.list(tab="give")
        self.assertEqual(out["proposals"], [])
        self.assertEqual(self.names(out), ["ASK"])
        self.assertEqual(out["rows"][0]["awaiting"], 1)
        self.me(F.BOB)
        self.assertEqual([a["request"] for a in self.q.list()["asks"]], ["AR1"])     # back in Bob's "Cần đồng ý"


# ------------------------------------------------------------------ FE-BE contract (pm_queue.js reads)
class TestQueueContract(Base):
    TOP = {"today", "now", "tab", "rows", "counts", "buckets", "asks", "personal_hidden", "waiting", "proposals",
           "truncated"}
    ROW = {"name", "subject", "bucket", "rank", "due", "due_time", "priority", "workflow_state", "self", "giver",
           "giver_name", "assignees", "project_name", "group", "review", "unopened", "giver_left", "awaiting",
           "progress"}
    ASK = {"request", "task", "subject", "from_name", "from_user", "proposed_end", "project_name", "message"}
    COUNTER = {"request", "recipient", "recipient_name", "due", "time", "start", "old_due", "old_time", "reason"}

    def test_every_field_pm_queue_reads_is_returned(self):
        F.task(self.fk, "MINE", owner=F.GIVER, assign=[F.ALICE], end="2026-10-16")
        F.task(self.fk, "ASKED", owner=F.GIVER, assign=[], state="Backlog")
        self.fk.add("PM Assignment Request", name="AR0", task="ASKED", recipient=F.ALICE, requested_by=F.GIVER,
                    status="Pending", kind="Assignment", proposed_end="2026-10-20 18:00:00")
        F.task(self.fk, "GAVE", owner=F.ALICE, assign=[F.BOB], end="2026-10-20")
        F.task(self.fk, "PROP", owner=F.ALICE, assign=[], state="Backlog")
        self.fk.add("PM Assignment Request", name="AR1", task="PROP", recipient=F.BOB, requested_by=F.ALICE,
                    status="Reschedule Proposed", kind="Assignment", counter_end="2026-10-22 17:30:00",
                    response_reason="ban")
        self.me()
        me, give = self.q.list(), self.q.list(tab="give")
        for out in (me, give):
            self.assertTrue(self.TOP <= set(out), self.TOP - set(out))
            for r in out["rows"] + out["waiting"] + out["proposals"]:
                self.assertTrue(self.ROW <= set(r), (r["name"], self.ROW - set(r)))
                self.assertFalse({"_assign", "_people", "exp_end_date", "pm_end_time"} & set(r))
        self.assertTrue(self.ASK <= set(me["asks"][0]), self.ASK - set(me["asks"][0]))
        self.assertTrue({"user", "name", "opened", "pending", "done", "left"} <= set(give["rows"][0]["assignees"][0]))
        self.assertTrue(self.COUNTER <= set(give["proposals"][0]["counter"]))


if __name__ == "__main__":
    unittest.main()

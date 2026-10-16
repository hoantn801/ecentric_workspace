# -*- coding: utf-8 -*-
"""PM redesign BE - pm_inbox endpoints (fake frappe, no bench).

Run:  cd src && python3 -m unittest discover -s ecentric_workspace/pm/tests/standalone -p 'test_redesign_*.py'
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.inbox = self.fk.load("ecentric_workspace.pm.api.pm_inbox")
        self.asg = self.fk.load("ecentric_workspace.pm.api.assignment")
        self.fk.hooks["PM Assignment Request"] = [self.asg.pm_assignment_request_guard]

    def as_user(self, u):
        self.fk.set_user(u)

    def events(self, event_type):
        return [n for n in self.fk.notifications if n["event_type"] == event_type]


# ------------------------------------------------------------------ request / answer / withdraw
class TestDeadlineFlow(Base):
    def setUp(self):
        super(TestDeadlineFlow, self).setUp()
        self.fk.add("Project", name="P1", project_name="Du an 1", expected_end_date="2026-12-31")
        F.task(self.fk, "PAR", owner=F.GIVER, assign=[F.GIVER], is_group=1, split=1,
               project="P1", start="2026-10-01", end="2026-10-20")
        F.task(self.fk, "T1", owner=F.GIVER, assign=[F.ALICE], project="P1",
               parent_task="PAR", start="2026-10-01", end="2026-10-18")

    def test_request_creates_deadline_request_and_notifies_giver(self):
        self.as_user(F.ALICE)
        r = self.inbox.request_deadline("T1", "2026-10-19", "Cho so lieu")
        self.assertEqual(r["status"], "Pending")
        self.assertEqual(r["old_end"], "2026-10-18")
        req = self.fk.row("PM Assignment Request", r["request"])
        self.assertEqual(req["kind"], "Deadline")
        self.assertEqual(req["recipient"], F.GIVER)
        self.assertEqual(req["requested_by"], F.ALICE)
        self.assertEqual(req["open_task_key"], "DL::T1")
        ev = self.events("task_deadline_requested")
        self.assertEqual([e["user"] for e in ev], [F.GIVER])
        # nothing changed on the task yet
        self.assertEqual(self.fk.row("Task", "T1")["exp_end_date"], "2026-10-18")

    def test_request_only_by_assignee(self):
        self.as_user(F.BOB)
        with self.assertRaises(F.PermissionError):
            self.inbox.request_deadline("T1", "2026-10-19", "x")

    def test_request_needs_reason_and_rejects_duplicates(self):
        self.as_user(F.ALICE)
        with self.assertRaises(F.ValidationError):
            self.inbox.request_deadline("T1", "2026-10-19", "  ")
        self.inbox.request_deadline("T1", "2026-10-19", "ly do")
        with self.assertRaises(F.ValidationError):
            self.inbox.request_deadline("T1", "2026-10-21", "lan hai")

    def test_request_bad_date_is_friendly(self):
        self.as_user(F.ALICE)
        with self.assertRaises(F.ValidationError):
            self.inbox.request_deadline("T1", "2026-02-30", "x")
        with self.assertRaises(F.ValidationError):
            self.inbox.request_deadline("T1", "2026-09-01", "truoc ngay bat dau")

    def test_answer_accept_within_parent_does_not_touch_parent(self):
        self.as_user(F.ALICE)
        req = self.inbox.request_deadline("T1", "2026-10-19", "x")["request"]
        self.as_user(F.GIVER)
        out = self.inbox.answer_deadline(req, 1, "ok")
        self.assertEqual(out["status"], "Accepted")
        self.assertFalse(out["parent_extended"])
        self.assertEqual(self.fk.row("Task", "T1")["exp_end_date"], "2026-10-19")
        self.assertEqual(self.fk.row("Task", "PAR")["exp_end_date"], "2026-10-20")
        self.assertIsNone(self.fk.row("PM Assignment Request", req)["open_task_key"])
        self.assertEqual([e["user"] for e in self.events("task_deadline_answered")], [F.ALICE])

    def test_answer_accept_past_parent_extends_parent_only_after_accept(self):
        self.as_user(F.ALICE)
        req = self.inbox.request_deadline("T1", "2026-10-25", "x")["request"]
        self.assertEqual(self.fk.row("Task", "PAR")["exp_end_date"], "2026-10-20")  # gated
        self.as_user(F.GIVER)
        out = self.inbox.answer_deadline(req, "1")
        self.assertTrue(out["parent_extended"])
        self.assertEqual(str(self.fk.row("Task", "PAR")["exp_end_date"]), "2026-10-25")
        self.assertEqual(self.fk.row("Task", "T1")["exp_end_date"], "2026-10-25")

    def test_answer_reject_keeps_date(self):
        self.as_user(F.ALICE)
        req = self.inbox.request_deadline("T1", "2026-10-25", "x")["request"]
        self.as_user(F.GIVER)
        out = self.inbox.answer_deadline(req, 0, "giu han")
        self.assertEqual(out["status"], "Rejected")
        self.assertEqual(self.fk.row("Task", "T1")["exp_end_date"], "2026-10-18")
        self.assertEqual(self.fk.row("PM Assignment Request", req)["response_reason"], "giu han")

    def test_answer_by_non_giver_denied_leader_allowed(self):
        self.as_user(F.ALICE)
        req = self.inbox.request_deadline("T1", "2026-10-19", "x")["request"]
        for u in (F.ALICE, F.BOB):
            self.as_user(u)
            with self.assertRaises(F.PermissionError):
                self.inbox.answer_deadline(req, 1)
        self.as_user(F.LEADER)
        self.assertEqual(self.inbox.answer_deadline(req, 1)["status"], "Accepted")
        with self.assertRaises(F.ValidationError):  # no longer pending
            self.inbox.answer_deadline(req, 1)

    def test_withdraw(self):
        self.as_user(F.ALICE)
        req = self.inbox.request_deadline("T1", "2026-10-19", "x")["request"]
        self.as_user(F.GIVER)
        with self.assertRaises(F.PermissionError):
            self.inbox.withdraw_deadline(req)
        self.as_user(F.ALICE)
        self.assertEqual(self.inbox.withdraw_deadline(req)["status"], "Cancelled")
        with self.assertRaises(F.ValidationError):
            self.inbox.withdraw_deadline(req)

    def test_old_assignment_api_refuses_deadline_requests(self):
        self.as_user(F.ALICE)
        req = self.inbox.request_deadline("T1", "2026-10-19", "x")["request"]
        self.as_user(F.GIVER)
        with self.assertRaises(F.ValidationError):
            self.asg.respond(req, "accept")          # giver is the request's recipient
        self.as_user(F.ALICE)
        with self.assertRaises(F.ValidationError):
            self.asg.requester_action(req, "cancel")  # Alice is its requested_by
        self.assertEqual(self.fk.row("PM Assignment Request", req)["status"], "Pending")

    def test_guard_blocks_writes_outside_service(self):
        self.as_user(F.ALICE)
        req = self.inbox.request_deadline("T1", "2026-10-19", "x")["request"]
        doc = self.fk.get_doc("PM Assignment Request", req)
        doc.status = "Accepted"
        with self.assertRaises(F.PermissionError):
            doc.save(ignore_permissions=True)


# ------------------------------------------------------------------ received
class TestReceived(Base):
    def setUp(self):
        super(TestReceived, self).setUp()
        self.fk.add("Project", name="WL", project_name="ERP - Nhat ky", ec_personal_log=1)
        F.task(self.fk, "NEW", owner=F.GIVER, assign=[F.ALICE], end="2026-10-30")
        F.task(self.fk, "MINE", owner=F.ALICE, assign=[F.ALICE])
        F.task(self.fk, "LOG", owner=F.GIVER, assign=[F.ALICE], project="WL")
        F.task(self.fk, "SUB", owner=F.GIVER, assign=['xalice@ec.vn'])  # substring trap
        F.task(self.fk, "REQ", owner=F.GIVER, assign=[], state="Backlog")
        self.fk.add("PM Assignment Request", name="AR1", task="REQ", recipient=F.ALICE,
                    requested_by=F.GIVER, status="Pending", kind="Assignment",
                    proposed_end="2026-10-25 00:00:00", message="nhan nhe")

    def test_received_shapes_and_badge(self):
        self.as_user(F.ALICE)
        r = self.inbox.received()
        self.assertEqual([x["request"] for x in r["needs_reply"]], ["AR1"])
        nr = r["needs_reply"][0]
        for k in ("request", "task", "subject", "project_name", "from_user", "from_name",
                  "proposed_end", "message", "created"):
            self.assertIn(k, nr)
        self.assertEqual(nr["from_name"], "Gia Ver")
        self.assertEqual([x["task"] for x in r["unopened"]], ["NEW"])  # not MINE / LOG / SUB
        self.assertEqual(r["unopened"][0]["from_user"], F.GIVER)
        self.assertEqual(r["badge"], 2)

    def test_opening_task_clears_unopened(self):
        tasks = self.fk.load("ecentric_workspace.pm.api.tasks")
        self.as_user(F.ALICE)
        tasks.get("NEW")
        self.assertTrue(self.fk.module.local.flags.commit)  # GET-safe tracking write
        self.assertEqual(self.inbox.received()["unopened"], [])

    def test_rejected_unseen_counts_until_task_opened(self):
        tasks = self.fk.load("ecentric_workspace.pm.api.tasks")
        self.as_user(F.ALICE)
        tasks.get("NEW")
        req = self.inbox.request_deadline("NEW", "2026-11-05", "ban")["request"]
        self.fk.advance(minutes=5)
        self.as_user(F.GIVER)
        self.inbox.answer_deadline(req, 0, "khong")
        self.as_user(F.ALICE)
        r = self.inbox.received()
        mine = r["my_deadline_requests"]
        self.assertEqual(mine[0]["status"], "Rejected")
        self.assertEqual(mine[0]["answer"], "khong")
        self.assertEqual(mine[0]["old_end"], "2026-10-30")
        self.assertEqual(r["badge"], 2)  # AR1 + rejected-unseen
        self.fk.advance(minutes=5)
        tasks.get("NEW")
        self.assertEqual(self.inbox.received()["badge"], 1)

    def test_requires_pm_access(self):
        self.as_user("nopm@ec.vn")
        with self.assertRaises(F.PermissionError):
            self.inbox.received()


# ------------------------------------------------------------------ given
class TestGiven(Base):
    def setUp(self):
        super(TestGiven, self).setUp()
        F.task(self.fk, "SP", owner=F.GIVER, assign=[F.GIVER], is_group=1, split=1,
               end="2026-10-10", auto_close=0, review=1)
        F.task(self.fk, "SP-A", owner=F.GIVER, assign=[F.ALICE], parent_task="SP",
               state="Done", completed_on="2026-10-12", end="2026-10-10",
               pm_checklist=[{"item_label": "a", "is_done": 1, "is_required": 1},
                             {"item_label": "b", "is_done": 0, "is_required": 0}])
        F.task(self.fk, "SP-B", owner=F.GIVER, assign=[F.BOB], parent_task="SP", end="2026-10-10")
        F.task(self.fk, "SOLO", owner=F.GIVER, assign=[F.GIVER])          # my own to-do
        F.task(self.fk, "OLD", owner=F.GIVER, assign=[F.BOB], state="Done", completed_on="2026-10-01")
        self.fk.add("PM Task Seen", name="SP-A::" + F.ALICE, task="SP-A", user=F.ALICE,
                    first_seen="2026-10-02 09:00:00", last_seen="2026-10-02 09:00:00")
        self.fk.add("PM Recurrence", name="R1", owner=F.GIVER, template_subject="Bao cao thang",
                    frequency="Monthly", interval=1, monthly_day=5, weekly_days="[]",
                    template_assignees=json.dumps([F.ALICE]), next_run_date="2026-11-05",
                    status="Active", last_task="OLD")

    def test_run_tab_batches(self):
        self.as_user(F.GIVER)
        r = self.inbox.given("run")
        self.assertEqual([b["task"] for b in r["batches"]], ["SP"])
        b = r["batches"][0]
        self.assertTrue(b["split"])
        self.assertEqual(b["review_required"], 1)
        self.assertEqual((b["done_count"], b["total"]), (1, 2))
        pa = [p for p in b["people"] if p["user"] == F.ALICE][0]
        self.assertTrue(pa["opened"])
        self.assertEqual(pa["done_on"], "2026-10-12")
        self.assertTrue(pa["late"])
        self.assertEqual(pa["steps"], "1/2")
        self.assertEqual(pa["full_name"], "Alice")
        pb = [p for p in b["people"] if p["user"] == F.BOB][0]
        self.assertFalse(pb["opened"])
        self.assertTrue(pb["late"])  # due 10/10, today 16/10, not done

    def test_done_and_rep_tabs(self):
        self.as_user(F.GIVER)
        d = self.inbox.given("done")
        self.assertEqual([b["task"] for b in d["batches"]], ["OLD"])
        self.assertEqual(d["batches"][0]["recurrence"]["name"], "R1")
        rep = self.inbox.given("rep")
        self.assertEqual(rep["rules"][0]["schedule_label"], "Hằng tháng ngày 5")
        self.assertEqual(rep["rules"][0]["assignees"][0]["full_name"], "Alice")

    def test_banner_lists_deadline_requests_for_me(self):
        self.as_user(F.BOB)
        self.inbox.request_deadline("SP-B", "2026-10-20", "tre")
        self.as_user(F.GIVER)
        banner = self.inbox.given("run")["banner"]
        self.assertEqual([x["task"] for x in banner], ["SP-B"])
        self.assertEqual(banner[0]["new_end"], "2026-10-20")
        self.as_user(F.ALICE)
        self.assertEqual(self.inbox.given("run")["banner"], [])

    def test_bad_tab(self):
        self.as_user(F.GIVER)
        with self.assertRaises(F.ValidationError):
            self.inbox.given("xyz")


# ------------------------------------------------------------------ coordinate
class TestCoordinate(Base):
    def setUp(self):
        super(TestCoordinate, self).setUp()
        self.fk.add("Project", name="P1", project_name="Du an 1", ec_manager=F.GIVER)
        self.fk.add("Project", name="WL", project_name="ERP - log", ec_personal_log=1)
        F.task(self.fk, "LATE", assign=[F.ALICE], project="P1", end="2026-10-01")
        F.task(self.fk, "FREE", assign=[], project="P1", end="2026-10-30")
        F.task(self.fk, "NODUE", assign=[F.BOB], project="P1", creation="2026-10-01 09:00:00")
        F.task(self.fk, "NEWNODUE", assign=[F.BOB], project="P1")  # < 7 days old: not a to-do
        F.task(self.fk, "OK", assign=[F.ALICE], project="P1", state="Done",
               end="2026-10-20", completed_on="2026-10-15")
        F.task(self.fk, "SLOW", assign=[F.ALICE], project="P1", state="Done",
               end="2026-10-10", completed_on="2026-10-12")
        F.task(self.fk, "LOG1", assign=[F.ALICE], project="WL", end="2026-09-01")

    def test_leader_view(self):
        self.as_user(F.LEADER)
        r = self.inbox.coordinate()
        self.assertEqual(r["kpi"], {"open": 4, "late": 1, "unassigned": 1, "done_week": 2,
                                    "on_time_pct_30d": 50})
        kinds = sorted(x["kind"] for x in r["todo"])
        self.assertEqual(kinds, ["late", "nodue", "unassigned"])
        alice = [p for p in r["people"] if p["user"] == F.ALICE][0]
        self.assertEqual((alice["open"], alice["late"], alice["done_week"]), (1, 1, 2))
        self.assertNotIn("on_time_pct", alice)
        p1 = r["projects"][0]
        self.assertEqual((p1["name"], p1["done"], p1["total"], p1["open"], p1["late"],
                          p1["unassigned"], p1["owner"]), ("P1", 2, 6, 4, 1, 1, F.GIVER))
        with_log = self.inbox.coordinate(include_personal=1)
        self.assertEqual(with_log["kpi"]["late"], 2)

    def test_non_leader_denied(self):
        self.as_user(F.GIVER)
        with self.assertRaises(F.PermissionError):
            self.inbox.coordinate()


# ------------------------------------------------------------------ nudge
class TestNudge(Base):
    def setUp(self):
        super(TestNudge, self).setUp()
        F.task(self.fk, "SP", owner=F.GIVER, assign=[F.GIVER], is_group=1, split=1)
        F.task(self.fk, "SP-A", owner=F.GIVER, assign=[F.ALICE], parent_task="SP", state="Done")
        F.task(self.fk, "SP-B", owner=F.GIVER, assign=[F.BOB], parent_task="SP")

    def test_nudge_not_done_only_and_rate_limit(self):
        self.as_user(F.GIVER)
        r = self.inbox.nudge("SP")
        self.assertEqual(r["sent"], [F.BOB])
        ev = self.events("task_nudge")
        self.assertEqual((ev[0]["user"], ev[0]["task"]), (F.BOB, "SP-B"))
        again = self.inbox.nudge("SP", users=json.dumps([F.BOB]))
        self.assertEqual((again["sent"], again["skipped"]), ([], [F.BOB]))
        self.fk.advance(minutes=61)
        self.assertEqual(self.inbox.nudge("SP")["sent"], [F.BOB])

    def test_nudge_permission_and_empty(self):
        self.as_user(F.ALICE)
        with self.assertRaises(F.PermissionError):
            self.inbox.nudge("SP")
        self.as_user(F.GIVER)
        with self.assertRaises(F.ValidationError):
            self.inbox.nudge("SP", users=[F.ALICE])  # Alice is done


# ------------------------------------------------------------------ close_parent
class TestCloseParent(Base):
    def setUp(self):
        super(TestCloseParent, self).setUp()
        F.task(self.fk, "SP", owner=F.GIVER, assign=[F.GIVER], is_group=1, split=1, state="Review")
        F.task(self.fk, "SP-A", owner=F.GIVER, assign=[F.ALICE], parent_task="SP", state="Done",
               completed_on="2026-10-15")
        F.task(self.fk, "SP-B", owner=F.GIVER, assign=[F.BOB], parent_task="SP", state="Done",
               completed_on="2026-10-15")

    def test_close(self):
        self.as_user(F.GIVER)
        r = self.inbox.close_parent("SP")
        self.assertEqual(r["state"], "Done")
        row = self.fk.row("Task", "SP")
        self.assertEqual((row["workflow_state"], row["completed_on"]), ("Done", "2026-10-16"))
        self.assertIn(("Version", ), [(d,) for d, _ in self.fk.inserted if d == "Version"])

    def test_return_one_person(self):
        self.as_user(F.GIVER)
        r = self.inbox.close_parent("SP", return_users=[F.BOB], note="Sua lai so")
        self.assertEqual(r["returned"], ["SP-B"])
        self.assertEqual(self.fk.row("Task", "SP-B")["workflow_state"], "In Progress")
        self.assertIsNone(self.fk.row("Task", "SP-B")["completed_on"])
        self.assertEqual(self.fk.row("Task", "SP")["workflow_state"], "In Progress")
        self.assertIn(("Task", "SP-B", "Comment", "Sua lai so"), self.fk.comments)

    def test_close_permission(self):
        self.as_user(F.ALICE)
        with self.assertRaises(F.PermissionError):
            self.inbox.close_parent("SP")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""04/11/2026 (phuong.nguyen): "Mỗi người một việc" + "Cần đồng ý" - the recipient pressed Nhận
việc on her part and got "Not permitted to adjust the date range of parent task …":
  1) _expand_ancestor_dates / _expand_project_dates checked permission on the parent / project
     even when nothing had to widen (a split-part recipient usually cannot open the parent);
  2) the part had already been finished by someone else, yet the request stayed Pending and kept
     showing in "Cần bạn trả lời" (live: 29 of 48 open requests were on Done tasks).
Fake frappe, no bench."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.tasks = self.fk.load("ecentric_workspace.pm.api.tasks")
        self.inbox = self.fk.load("ecentric_workspace.pm.api.pm_inbox")
        self.asg = self.fk.load("ecentric_workspace.pm.api.assignment")
        self.fk.hooks["PM Assignment Request"] = [self.asg.pm_assignment_request_guard]
        self.fk.add("Project", name="P1", project_name="Ke hoach", owner=F.GIVER,
                    expected_end_date="2026-10-31")
        F.task(self.fk, "PAR", owner=F.GIVER, assign=[], is_group=1, split=1, project="P1",
               end="2026-10-22")
        F.task(self.fk, "PART", owner=F.GIVER, assign=[], parent_task="PAR", project="P1",
               state="To Do", end="2026-10-22")
        self.req("AR", "PART", "2026-10-22 18:00:00")

    def req(self, name, task, end, by=F.GIVER):
        self.fk.add("PM Assignment Request", name=name, task=task, recipient=F.ALICE,
                    requested_by=by, status="Pending", kind="Assignment", proposed_end=end,
                    open_task_key=task, open_request_key=task + "::" + F.ALICE)

    def status(self, name):
        return self.fk.row("PM Assignment Request", name)["status"]

    def as_user(self, u):
        self.fk.set_user(u)


class TestAcceptPart(Base):
    def test_recipient_cannot_open_parent_but_dates_fit_accepts(self):
        self.as_user(F.ALICE)
        self.asg.respond("AR", "accept")
        self.assertEqual(self.status("AR"), "Accepted")
        self.assertIn(F.ALICE, self.fk.row("Task", "PART").get("_assign") or "")

    def test_widening_is_backed_by_the_requester(self):
        self.fk.row("PM Assignment Request", "AR")["proposed_end"] = "2026-10-25 18:00:00"
        self.as_user(F.ALICE)
        self.asg.respond("AR", "accept")
        self.assertEqual(str(self.fk.row("Task", "PAR")["exp_end_date"])[:10], "2026-10-25")

    def test_widening_still_needs_someone_allowed(self):
        F.task(self.fk, "PAR2", owner=F.GIVER, assign=[], is_group=1, split=1, project="P1",
               end="2026-10-22")
        F.task(self.fk, "PART2", owner=F.GIVER, assign=[], parent_task="PAR2", project="P1",
               state="To Do", end="2026-10-22")
        self.req("AR2", "PART2", "2026-10-28 18:00:00", by=F.OUTSIDER)
        self.as_user(F.ALICE)
        with self.assertRaises(F.PermissionError):
            self.asg.respond("AR2", "accept")


class TestFinishedPart(Base):
    def test_answering_a_finished_part_closes_the_request(self):
        self.fk.row("Task", "PART")["workflow_state"] = "Done"
        self.fk.row("Task", "PART")["status"] = "Completed"
        self.as_user(F.ALICE)
        out = self.asg.respond("AR", "accept")
        self.assertEqual(out.get("auto_closed"), 1)
        self.assertEqual(self.status("AR"), "Cancelled")
        self.assertIsNone(self.fk.row("PM Assignment Request", "AR").get("open_task_key"))

    def test_finished_part_not_listed_in_needs_reply(self):
        self.fk.row("Task", "PART")["workflow_state"] = "Done"
        self.as_user(F.ALICE)
        self.assertEqual(self.inbox.received()["needs_reply"], [])

    def test_state_write_to_done_closes_open_requests(self):
        self.fk.row("Task", "PART")["workflow_state"] = "To Do"
        self.as_user(F.GIVER)
        self.tasks.set_status("PART", "Done")
        self.assertEqual(self.status("AR"), "Cancelled")
        self.as_user(F.ALICE)
        self.assertEqual(self.inbox.received()["needs_reply"], [])

    def test_open_part_still_listed(self):
        self.as_user(F.ALICE)
        self.assertEqual([x["request"] for x in self.inbox.received()["needs_reply"]], ["AR"])

    def test_p031_cleans_old_rows_once(self):
        self.fk.row("Task", "PART")["workflow_state"] = "Done"
        F.task(self.fk, "LIVE", owner=F.GIVER, assign=[], end="2026-10-30")
        self.req("AR3", "LIVE", "2026-10-30 18:00:00")
        p031 = self.fk.load("ecentric_workspace.pm.patches.p031_pm_close_requests_on_finished_tasks")
        p031.execute()
        self.assertEqual((self.status("AR"), self.status("AR3")), ("Cancelled", "Pending"))
        p031.execute()   # idempotent
        self.assertEqual(self.status("AR3"), "Pending")
        with open(os.path.join(F.SRC, "ecentric_workspace", "patches.txt")) as fh:
            self.assertIn("ecentric_workspace.pm.patches.p031_pm_close_requests_on_finished_tasks",
                          [l.strip() for l in fh])


if __name__ == "__main__":
    unittest.main()

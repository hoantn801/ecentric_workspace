# -*- coding: utf-8 -*-
"""Tester t3 (03/11/2026) - backend behind the /pm host page:
  * schedule.week: a block belongs to the week of its START (blocks ending at next Monday 00:00
    or running past midnight used to vanish from both weeks);
  * schedule.week: department heads keep the "Xem lịch người khác" picker (can_view_others);
  * schedule.confirm: negative / non-finite hours are refused before anything is written;
  * tasks.transitions_bulk: view-only users get no transitions (Kanban card locked);
  * pm_overdue_scan / pm_due_soon_scan: an open split parent (coordination row of the giver) is
    not reminded on top of its parts.
Fake frappe, no bench."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402

BLOCK = "EC PM Time Block"
VIEWER = "viewer@ec.vn"


def _sched(fk):
    u = fk.utils   # schedule.py also imports time_diff_in_hours (not in the shared fake)
    u.time_diff_in_hours = lambda a, b: (u.get_datetime(a) - u.get_datetime(b)).total_seconds() / 3600.0
    m = fk.load("ecentric_workspace.pm.api.schedule")
    m._ms_meetings = lambda *a, **k: []
    return m


class TestScheduleWeek(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.s = _sched(self.fk)
        self.fk.set_user(F.ALICE)
        F.task(self.fk, "T1", owner=F.ALICE, assign=[F.ALICE])
        add = lambda n, a, b: self.fk.add(BLOCK, name=n, task="T1", user=F.ALICE, start=a, end=b,
                                          hours=1, state="Dự kiến")
        # week of Mon 2026-10-12 .. Sun 2026-10-18
        add("in", "2026-10-14 09:00:00", "2026-10-14 10:00:00")
        add("sun-midnight", "2026-10-18 23:00:00", "2026-10-19 00:00:00")
        add("cross", "2026-10-15 22:00:00", "2026-10-16 01:00:00")
        add("prev-week", "2026-10-11 23:00:00", "2026-10-12 00:00:00")
        add("next-week", "2026-10-19 08:00:00", "2026-10-19 09:00:00")

    def test_blocks_by_start_day(self):
        r = self.s.week(week_start="2026-10-14")
        got = sorted(b["name"] for b in r["blocks"])
        self.assertEqual(got, ["cross", "in", "sun-midnight"])

    def test_previous_week_keeps_its_sunday_block(self):
        r = self.s.week(week_start="2026-10-05")
        self.assertEqual([b["name"] for b in r["blocks"]], ["prev-week"])

    def test_head_without_team_keeps_picker(self):
        self.s._team_user_ids = lambda u: []
        self.s._headed_staff_ids = lambda u: []
        self.assertFalse(self.s.week(week_start="2026-10-14")["can_view_others"])
        self.s._headed_staff_ids = lambda u: [F.BOB] if u == F.ALICE else []
        self.assertTrue(self.s.week(week_start="2026-10-14")["can_view_others"])


class TestScheduleConfirm(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.s = _sched(self.fk)
        self.synced = []
        self.s._sync_timesheet = lambda user, b, hrs: self.synced.append((b["name"], hrs)) or "TS-" + b["name"]
        self.s._pending_names_for = lambda u: []
        self.s._close_nudge_todo = lambda u: None
        self.fk.set_user(F.ALICE)
        for n in ("B1", "B2"):
            self.fk.add(BLOCK, name=n, task="T1", user=F.ALICE, start="2026-10-15 09:00:00",
                        end="2026-10-15 10:30:00", hours=1.5, state="Dự kiến", timesheet=None)

    def test_negative_hours_refused_nothing_written(self):
        with self.assertRaises(F.ValidationError):
            self.s.confirm('["B1","B2"]', '{"B1": 2, "B2": -1}')
        self.assertEqual(self.synced, [])
        self.assertEqual(self.fk.row(BLOCK, "B1")["state"], "Dự kiến")

    def test_nan_refused(self):
        with self.assertRaises(F.ValidationError):
            self.s.confirm('["B1"]', '{"B1": "nan"}')
        with self.assertRaises(F.ValidationError):
            self.s.confirm('["B1"]', '{"B1": "inf"}')

    def test_blank_keeps_planned_valid_rounded(self):
        r = self.s.confirm('["B1","B2"]', '{"B1": "", "B2": "2.345"}')
        self.assertEqual(sorted(r["confirmed"]), ["B1", "B2"])
        self.assertEqual(dict(self.synced), {"B1": 1.5, "B2": 2.35})
        self.assertEqual(self.fk.row(BLOCK, "B2")["hours"], 2.35)
        self.assertEqual(self.fk.row(BLOCK, "B2")["state"], "Đã xác nhận")

    def test_other_users_block_ignored(self):
        self.fk.add(BLOCK, name="BX", task="T1", user=F.BOB, start="2026-10-15 09:00:00",
                    end="2026-10-15 10:00:00", hours=1, state="Dự kiến", timesheet=None)
        r = self.s.confirm('["BX"]', '{"BX": 3}')
        self.assertEqual(r["confirmed"], [])
        self.assertEqual(self.fk.row(BLOCK, "BX")["state"], "Dự kiến")


class TestTransitionsBulkViewOnly(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.fk.add("User", name=VIEWER, full_name="Viewer", enabled=1, user_type="System User")
        self.fk.roles[VIEWER] = ["PM Member"]
        self.fk.add("Project", name="P1", project_name="Du an 1")
        self.tasks = self.fk.load("ecentric_workspace.pm.api.tasks")
        self.pmperm = self.fk.load("ecentric_workspace.pm.permissions")
        F.task(self.fk, "T", owner=F.GIVER, assign=[F.ALICE], project="P1", state="To Do")
        real = self.pmperm.can_view_task
        self.pmperm.can_view_task = lambda t, u=None: (u or self.fk.session.user) == VIEWER or real(t, u)

    def test_viewer_gets_no_transitions(self):
        self.fk.set_user(VIEWER)
        m = self.tasks.transitions_bulk('["T"]')["map"]
        self.assertIn("T", m)
        self.assertEqual(m["T"]["transitions"], [])
        self.assertFalse(m["T"]["can_edit"])

    def test_assignee_still_gets_transitions(self):
        self.fk.set_user(F.ALICE)
        m = self.tasks.transitions_bulk('["T"]')["map"]
        self.assertTrue(m["T"]["transitions"])
        self.assertTrue(m["T"]["can_edit"])


class TestScansSplitParent(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.sent = []
        # the real notifications module, with its outbound dependencies stubbed
        for k in list(sys.modules):
            if k == "ecentric_workspace.pm.api.notifications":
                sys.modules.pop(k)
        stub = lambda name, **attrs: sys.modules.__setitem__(name, types.SimpleNamespace(**attrs))
        stub("ecentric_workspace.notification_center.nhip_gui", gop_tin_job=lambda f: f)
        stub("ecentric_workspace.notification_center.events",
             publish_notification_event=lambda et, u, subj, msg, **k: self.sent.append((et, u, k.get("reference_name"))))
        stub("ecentric_workspace.action_center.resolvers", build_pm_task_url=lambda n: "/pm#task/" + n)
        stub("ecentric_workspace.approval_center.shared.workflow.ngay_lam_viec",
             nguoi_di_lam=lambda users, day: list(users))
        import ecentric_workspace.notification_center  # noqa: F401  (package placeholder)
        self.n = self.fk.load("ecentric_workspace.pm.api.notifications")
        self.n._notify_followers_overdue = lambda t, d: None
        # overdue split parent (giver's coordination row) + two parts, one done
        F.task(self.fk, "P", owner=F.GIVER, assign=[F.GIVER], end="2026-10-10", split=1, is_group=1)
        F.task(self.fk, "C1", owner=F.GIVER, assign=[F.ALICE], end="2026-10-10", parent_task="P")
        F.task(self.fk, "C2", owner=F.GIVER, assign=[F.BOB], end="2026-10-10", parent_task="P", state="Done")
        F.task(self.fk, "N", owner=F.GIVER, assign=[F.GIVER], end="2026-10-10")

    def who(self, event):
        return sorted((u, t) for et, u, t in self.sent if et == event)

    def test_overdue_open_split_parent_not_reminded(self):
        self.n.pm_overdue_scan()
        self.assertEqual(self.who("task_overdue"), [(F.ALICE, "C1"), (F.GIVER, "N")])

    def test_overdue_parent_in_review_is_reminded(self):
        self.fk.row("Task", "C1").update(workflow_state="Done", status="Completed")
        self.fk.row("Task", "P").update(workflow_state="Review")
        self.n.pm_overdue_scan()
        self.assertEqual(self.who("task_overdue"), [(F.GIVER, "N"), (F.GIVER, "P")])

    def test_due_soon_open_split_parent_not_reminded(self):
        for n in ("P", "C1", "C2", "N"):
            self.fk.row("Task", n)["exp_end_date"] = "2026-10-17"
        self.n.pm_due_soon_scan()
        self.assertEqual(self.who("task_due_soon"), [(F.ALICE, "C1"), (F.GIVER, "N")])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Backend review 03/11/2026 (tester t1) - regression tests for the bugs fixed in this pass.

  1. set_status("Done") bypassed the required-steps guard + did not withdraw "xin dời hạn".
  2. checklist.complete_task bypassed "Cần người giao kiểm tra" and the split roll-up.
  3. Reopening / undoing a split part left its rolled-up parent in Review / Done.
  4. tasks.update could move a task INTO a project the caller cannot see.
  5. PM Recurrence: any project viewer could edit / pause / cancel someone else's rule; a rule
     could target a project the creator cannot see; recurrence.list was N+1.
  6. "Được giao cho tôi -> chưa mở" listed occurrences of the user's OWN recurrence rule.
  7. Date-only assignment windows stored pm_*_time = 00:00:00, which later blocked every
     same-day start time ("kết thúc trước bắt đầu").
  8. Overdue scan told followers twice for a split parent (parent + each late part).
  9. transitions_bulk loaded every task doc (N+1) - now batched, same result.
 10. Recurrence occurrences were owned by whoever ran the generation (Administrator for the
     scheduler): every occurrence but the rule's latest lost its giver.
"""
import importlib.util
import json
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402

VIEWER = "viewer@ec.vn"
PM_BOSS = "pmboss@ec.vn"


class Base(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        for u in (VIEWER, PM_BOSS):
            self.fk.add("User", name=u, full_name=u, enabled=1, user_type="System User")
            self.fk.roles[u] = ["PM Member"]
        self.tasks = self.fk.load("ecentric_workspace.pm.api.tasks")
        self.asg = self.fk.load("ecentric_workspace.pm.api.assignment")
        self.inbox = self.fk.load("ecentric_workspace.pm.api.pm_inbox")
        self.fk.hooks["PM Assignment Request"] = [self.asg.pm_assignment_request_guard]

    def as_user(self, u):
        self.fk.set_user(u)

    def state(self, name):
        return self.fk.row("Task", name)["workflow_state"]


# ------------------------------------------------------------------ 1. set_status Done guards
class TestSetStatusDoneGuards(Base):
    def test_required_steps_block_set_status_done(self):
        F.task(self.fk, "T", assign=[F.ALICE],
               pm_checklist=[{"item_label": "a", "is_required": 1, "is_done": 0}])
        self.as_user(F.ALICE)
        with self.assertRaises(F.ValidationError):
            self.tasks.set_status("T", "Done")
        self.assertEqual(self.state("T"), "To Do")
        self.tasks.set_status("T", "In Progress")      # other states are not affected
        self.assertEqual(self.state("T"), "In Progress")

    def test_set_status_done_withdraws_deadline_request(self):
        F.task(self.fk, "T", assign=[F.ALICE], end="2026-10-20")
        self.as_user(F.ALICE)
        req = self.inbox.request_deadline("T", "2026-10-25", "x")["request"]
        self.tasks.set_status("T", "Done")
        self.assertEqual(self.state("T"), "Done")
        self.assertEqual(self.fk.row("PM Assignment Request", req)["status"], "Cancelled")


# ------------------------------------------------------------------ 2. checklist.complete_task
class TestChecklistCompleteTask(Base):
    def setUp(self):
        super(TestChecklistCompleteTask, self).setUp()
        self.ck = self.fk.load("ecentric_workspace.pm.api.checklist")
        fk = self.fk
        self.ck.get_transitions = lambda doc: [{"action": "Hoàn thành", "next_state": "Done"}]

        def apply_workflow(doc, action):
            fk.db.set_value("Task", doc.name, {"workflow_state": "Done", "status": "Completed"})
            return fk.get_doc("Task", doc.name)
        self.ck.apply_workflow = apply_workflow
        self.steps = [{"item_label": "a", "is_required": 1, "is_done": 1}]

    def test_review_required_cannot_be_closed_by_assignee(self):
        F.task(self.fk, "T", assign=[F.ALICE], review=1, pm_checklist=self.steps)
        self.as_user(F.ALICE)
        with self.assertRaises(F.PermissionError):
            self.ck.complete_task("T")
        self.assertEqual(self.state("T"), "To Do")
        self.as_user(F.GIVER)                           # the giver may close it
        self.assertEqual(self.ck.complete_task("T")["workflow_state"], "Done")

    def test_split_part_rolls_parent_up(self):
        F.task(self.fk, "P", assign=[F.GIVER], is_group=1, split=1)
        F.task(self.fk, "C1", assign=[F.ALICE], parent_task="P", state="Done")
        F.task(self.fk, "C2", assign=[F.BOB], parent_task="P", pm_checklist=self.steps)
        self.as_user(F.BOB)
        self.ck.complete_task("C2")
        self.assertEqual(self.state("P"), "Review")


# ------------------------------------------------------------------ 3. reopen a split part
class TestReopenSplitPart(Base):
    def _split(self, auto_close=0):
        F.task(self.fk, "P", assign=[F.GIVER], is_group=1, split=1, auto_close=auto_close)
        F.task(self.fk, "C1", assign=[F.ALICE], parent_task="P", state="Done")
        F.task(self.fk, "C2", assign=[F.BOB], parent_task="P", state="In Progress")

    def test_undo_last_part_puts_review_parent_back_in_progress(self):
        self._split()
        self.as_user(F.BOB)
        self.assertEqual(self.tasks.mark_done("C2").get("parent_state"), "Review")
        self.tasks.set_status("C2", "In Progress")      # "Hoàn tác" right after Xong
        self.assertEqual(self.state("C2"), "In Progress")
        self.assertEqual(self.state("P"), "In Progress")
        self.assertTrue(any(c[1] == "P" and "Mở lại" in (c[3] or "") for c in self.fk.comments))

    def test_reopen_after_auto_close(self):
        self._split(auto_close=1)
        self.as_user(F.BOB)
        self.tasks.mark_done("C2")
        self.assertEqual(self.state("P"), "Done")
        self.tasks.set_status("C2", "To Do")
        self.assertEqual(self.state("P"), "In Progress")
        self.assertIsNone(self.fk.row("Task", "P").get("completed_on"))

    def test_giver_returns_one_part_by_its_child(self):
        self._split()
        self.as_user(F.BOB)
        self.tasks.mark_done("C2")
        self.as_user(F.GIVER)
        self.inbox.close_parent("C2", return_users=[F.BOB])
        self.assertEqual((self.state("C2"), self.state("P")), ("In Progress", "In Progress"))

    def test_plain_task_reopen_untouched(self):
        F.task(self.fk, "P", assign=[F.GIVER], is_group=1, split=0, state="Review")
        F.task(self.fk, "C", assign=[F.ALICE], parent_task="P", state="Done")
        self.as_user(F.ALICE)
        self.tasks.set_status("C", "To Do")
        self.assertEqual(self.state("P"), "Review")


# ------------------------------------------------------------------ 4. update -> project
class TestUpdateProjectPermission(Base):
    def test_cannot_move_task_into_invisible_project(self):
        self.fk.add("Project", name="SECRET", project_name="Bi mat", ec_manager=F.BOB)
        self.fk.add("Project", name="MINE", project_name="Cua toi", ec_manager=F.ALICE)
        F.task(self.fk, "T", owner=F.ALICE, assign=[F.ALICE])
        self.as_user(F.ALICE)
        with self.assertRaises(F.PermissionError):
            self.tasks.update("T", project="SECRET")
        self.assertIsNone(self.fk.row("Task", "T")["project"])
        self.assertEqual(self.tasks.update("T", project="MINE")["changed"], ["project"])

    def test_unchanged_project_still_saves_other_fields(self):
        # an assignee who reaches the project only through the task keeps editing it
        self.fk.add("Project", name="SECRET", project_name="Bi mat", ec_manager=F.BOB)
        F.task(self.fk, "T", owner=F.BOB, assign=[F.ALICE], project="SECRET")
        self.as_user(F.ALICE)
        out = self.tasks.update("T", subject="Moi", project="SECRET")
        self.assertIn("subject", out["changed"])


# ------------------------------------------------------------------ 5. recurrence rules
class TestRecurrencePermission(Base):
    def setUp(self):
        super(TestRecurrencePermission, self).setUp()
        self.rec = self.fk.load("ecentric_workspace.pm.api.recurrence")
        self.fk.add("Project", name="P1", project_name="Du an 1", ec_manager=PM_BOSS)
        self.fk.add("Project User", name="PU1", parent="P1", user=VIEWER)   # VIEWER sees P1
        self.as_user(F.GIVER)
        self.fk.add("Project User", name="PU2", parent="P1", user=F.GIVER)
        self.rule = self.rec.create("Bao cao", "Daily", project="P1", assignees=[F.ALICE])["name"]

    def test_viewer_can_open_but_not_change(self):
        self.as_user(VIEWER)
        self.assertEqual(self.rec.get(self.rule)["can_edit"], 0)
        for fn in (lambda: self.rec.update_template(self.rule, subject="Hack"),
                   lambda: self.rec.pause(self.rule), lambda: self.rec.cancel(self.rule)):
            with self.assertRaises(F.PermissionError):
                fn()
        self.assertEqual(self.fk.row("PM Recurrence", self.rule)["status"], "Active")
        self.assertEqual(self.fk.row("PM Recurrence", self.rule)["template_subject"], "Bao cao")

    def test_responsible_people_still_can(self):
        for u in (F.GIVER, F.ALICE, PM_BOSS, F.LEADER):
            self.as_user(u)
            self.assertEqual(self.rec.get(self.rule)["can_edit"], 1, u)
        self.as_user(F.ALICE)
        self.assertEqual(self.rec.pause(self.rule)["status"], "Paused")
        self.as_user(F.GIVER)
        self.assertEqual(self.rec.resume(self.rule)["status"], "Active")

    def test_rule_cannot_target_invisible_project(self):
        self.fk.add("Project", name="SECRET", project_name="Bi mat", ec_manager=F.BOB)
        self.as_user(F.ALICE)
        with self.assertRaises(F.PermissionError):
            self.rec.create("X", "Daily", project="SECRET")
        self.as_user(F.GIVER)
        with self.assertRaises(F.PermissionError):
            self.rec.update_template(self.rule, project="SECRET")

    def test_list_scoped_without_per_row_lookups(self):
        self.as_user(F.BOB)
        mine = self.rec.create("Cua Bob", "Daily")["name"]
        calls = []
        real = self.rec.pmperm.can_view_project
        self.rec.pmperm.can_view_project = lambda *a, **k: calls.append(a) or real(*a, **k)
        try:
            self.assertEqual([r["name"] for r in self.rec.list()["rows"]], [mine])
            self.as_user(VIEWER)
            self.assertEqual([r["name"] for r in self.rec.list()["rows"]], [self.rule])
        finally:
            self.rec.pmperm.can_view_project = real
        self.assertEqual(calls, [])
        self.assertNotIn("owner", self.rec.list()["rows"][0])   # response shape unchanged


# ------------------------------------------------------------------ 6. unopened: own recurrence
class TestUnopenedOwnRecurrence(Base):
    def test_own_rule_occurrence_is_not_unopened(self):
        F.task(self.fk, "OCC", owner="Administrator", assign=[F.GIVER])
        self.fk.add("PM Recurrence", name="R1", owner=F.GIVER, last_task="OCC", status="Active")
        F.task(self.fk, "FROM_ALICE", owner=F.ALICE, assign=[F.GIVER])
        self.as_user(F.GIVER)
        got = [r["task"] for r in self.inbox.received()["unopened"]]
        self.assertEqual(got, ["FROM_ALICE"])


# ------------------------------------------------------------------ 7. midnight time artifact
class TestDateOnlyWindowHasNoMidnightTime(Base):
    def setUp(self):
        super(TestDateOnlyWindowHasNoMidnightTime, self).setUp()
        fk = self.fk

        def _task_default_state(doc, method=None):  # what the PM Task Workflow does on insert
            if not doc.get("workflow_state"):
                doc["workflow_state"] = "Backlog"
        fk.hooks["Task"] = [_task_default_state]

        def apply_workflow(doc, action):
            fk.db.set_value("Task", doc.name, "workflow_state", "To Do")
        self.asg.apply_workflow = apply_workflow

    def _sent(self, **kw):
        self.fk.module.local.form_dict = dict(kw)

    def test_create_and_accept_date_only_store_no_time(self):
        self.as_user(F.GIVER)
        r = self.asg.create_with_task("Bao cao", recipient=F.ALICE,
                                      proposed_start="2026-10-20", proposed_end="2026-10-20")
        row = self.fk.row("Task", r["task"])
        self.assertEqual((row["pm_start_time"], row["pm_end_time"]), (None, None))
        self.as_user(F.ALICE)
        self.asg.respond(r["request"]["name"], "accept")
        row = self.fk.row("Task", r["task"])
        self.assertEqual((row["pm_start_time"], row["pm_end_time"]), (None, None))
        # a same-day start time can now be set
        self._sent(name=r["task"], exp_start_date="2026-10-20", pm_start_time="09:00")
        self.tasks.update(r["task"], exp_start_date="2026-10-20", pm_start_time="09:00")
        self.assertEqual(self.fk.row("Task", r["task"])["pm_start_time"], "09:00:00")

    def test_real_time_is_kept(self):
        self.as_user(F.GIVER)
        r = self.asg.create_with_task("Bao cao", recipient=F.ALICE,
                                      proposed_end="2026-10-20 17:30")
        self.assertEqual(self.fk.row("Task", r["task"])["pm_end_time"], "17:30:00")

    def test_legacy_stored_midnight_does_not_block_start_time(self):
        F.task(self.fk, "T", owner=F.GIVER, assign=[F.ALICE], start="2026-10-20 00:00:00",
               end="2026-10-20 00:00:00", pm_start_time="0:00:00", pm_end_time="0:00:00")
        self.as_user(F.ALICE)
        self._sent(name="T", exp_start_date="2026-10-20", pm_start_time="09:00")
        self.tasks.update("T", exp_start_date="2026-10-20", pm_start_time="09:00")
        self.assertEqual(self.fk.row("Task", "T")["pm_start_time"], "09:00:00")
        # an explicitly sent end time before the start is still rejected
        self._sent(name="T", pm_end_time="08:00")
        with self.assertRaises(F.ValidationError):
            self.tasks.update("T", pm_end_time="08:00")

    def tearDown(self):
        self.fk.module.local.form_dict = {}


# ------------------------------------------------------------------ 8. overdue followers
def _load_real_notifications(fk):
    """The fake stubs pm.api.notifications; load the REAL file (scan code) with its
    notification-center dependencies stubbed."""
    published = []
    stubs = {
        "ecentric_workspace.notification_center": types.ModuleType("x"),
        "ecentric_workspace.notification_center.nhip_gui": types.ModuleType("x"),
        "ecentric_workspace.notification_center.events": types.ModuleType("x"),
        "ecentric_workspace.action_center": types.ModuleType("x"),
        "ecentric_workspace.action_center.resolvers": types.ModuleType("x"),
    }
    stubs["ecentric_workspace.notification_center.nhip_gui"].gop_tin_job = lambda f: f
    stubs["ecentric_workspace.notification_center.events"].publish_notification_event = \
        lambda ev, user, subject, msg, **kw: published.append((ev, user, subject, kw.get("dedupe_key")))
    stubs["ecentric_workspace.action_center.resolvers"].build_pm_task_url = lambda t: "/pm#task/" + t
    stubs["ecentric_workspace.notification_center"].nhip_gui = stubs["ecentric_workspace.notification_center.nhip_gui"]
    stubs["ecentric_workspace.notification_center"].events = stubs["ecentric_workspace.notification_center.events"]
    stubs["ecentric_workspace.action_center"].resolvers = stubs["ecentric_workspace.action_center.resolvers"]
    sys.modules.update(stubs)   # F.install() purges every ecentric_workspace module per test
    path = os.path.join(F.SRC, "ecentric_workspace", "pm", "api", "notifications.py")
    spec = importlib.util.spec_from_file_location("pm_notifications_real_t1", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._dang_lam = lambda users, day: list(users)
    return mod, published


class TestOverdueFollowersOnce(Base):
    def test_split_parent_does_not_double_notify_followers(self):
        F.task(self.fk, "P", owner=F.GIVER, assign=[F.GIVER], is_group=1, split=1,
               end="2026-10-10 00:00:00")
        F.task(self.fk, "C1", owner=F.GIVER, assign=[F.ALICE], parent_task="P",
               end="2026-10-10 00:00:00")
        self.fk.add("PM Task Follower", name="P::" + F.LEADER, task="P", user=F.LEADER,
                    source="Tự động", for_users=json.dumps([F.ALICE]))
        notif, published = _load_real_notifications(self.fk)
        notif.pm_overdue_scan()
        to_head = [p for p in published if p[1] == F.LEADER]
        self.assertEqual(len(to_head), 1, to_head)
        self.assertIn("C1", to_head[0][3])           # about Alice's part, not the parent
        # plain task followers still get their one notice
        F.task(self.fk, "T", owner=F.GIVER, assign=[F.BOB], end="2026-10-10 00:00:00")
        self.fk.add("PM Task Follower", name="T::" + F.LEADER, task="T", user=F.LEADER,
                    source="Thêm tay")
        notif.pm_overdue_scan()
        self.assertTrue(any(p[1] == F.LEADER and "|T|" in p[3] for p in published))


# ------------------------------------------------------------------ 9. transitions_bulk batched
class TestTransitionsBulkBatched(Base):
    def test_same_result_without_loading_docs(self):
        F.task(self.fk, "A", owner=F.ALICE, assign=[F.ALICE])
        F.task(self.fk, "B", owner=F.GIVER, assign=[F.ALICE], state="Done")
        F.task(self.fk, "HIDDEN", owner=F.BOB, assign=[F.BOB])
        loads = []
        real = self.fk.module.get_doc
        self.fk.module.get_doc = lambda dt, name=None, *a, **k: loads.append(name) or real(dt, name, *a, **k)
        self.as_user(F.ALICE)
        try:
            out = self.tasks.transitions_bulk(json.dumps(["A", "B", "HIDDEN", "MISSING", "A"]))["map"]
        finally:
            self.fk.module.get_doc = real
        self.assertEqual(sorted(out), ["A", "B"])
        self.assertEqual((out["A"]["current"], out["A"]["terminal"]), ("To Do", False))
        self.assertEqual((out["B"]["current"], out["B"]["terminal"]), ("Done", True))
        self.assertNotIn("Done", [t["next_state"] for t in out["B"]["transitions"]])
        self.assertEqual(loads, [])


# ------------------------------------------------------------------ 10. occurrence owner
class TestRecurrenceOccurrenceOwner(Base):
    def setUp(self):
        super(TestRecurrenceOccurrenceOwner, self).setUp()
        self.rec = self.fk.load("ecentric_workspace.pm.api.recurrence")
        self.tflow = self.fk.load("ecentric_workspace.pm.task_flow")

        def _task_default_state(doc, method=None):
            if not doc.get("workflow_state"):
                doc["workflow_state"] = "To Do"
        self.fk.hooks["Task"] = [_task_default_state]

    def _run(self, rule, day):
        self.as_user("Administrator")            # the 00:00 scheduler
        self.rec._process(rule, self.fk.utils.getdate(day))
        return self.fk.row("PM Recurrence", rule)["last_task"]

    def test_older_occurrence_keeps_rule_owner_as_giver(self):
        self.as_user(F.GIVER)
        rule = self.rec.create("Bao cao ngay", "Daily", assignees=[F.ALICE], review_required=1,
                               duration_days=1, start_date="2026-10-14",
                               checklist_items=json.dumps(["Keo so"]))["name"]
        first = self._run(rule, "2026-10-14")
        second = self._run(rule, "2026-10-15")
        self.assertNotEqual(first, second)
        for t in (first, second):
            self.assertEqual(self.fk.row("Task", t)["owner"], F.GIVER)   # survives t.save()
        old = self.fk.row("Task", first)
        self.assertEqual(self.tflow.giver_of(old), F.GIVER)
        self.assertTrue(self.tflow.can_edit_task({"name": first}, F.GIVER))
        # Alice's "xin dời hạn" on yesterday's occurrence reaches the rule owner
        self.as_user(F.ALICE)
        req = self.inbox.request_deadline(first, "2026-10-25", "ban")["request"]
        self.assertEqual(self.fk.row("PM Assignment Request", req)["recipient"], F.GIVER)

    def test_split_children_owned_by_rule_owner(self):
        self.as_user(F.GIVER)
        rule = self.rec.create("Bao cao", "Daily", assignees=[F.ALICE, F.BOB],
                               split_per_assignee=1, start_date="2026-10-16")["name"]
        parent = self._run(rule, "2026-10-16")
        kids = [t for t in self.fk.db.t("Task").values() if t.get("parent_task") == parent]
        self.assertEqual(len(kids), 2)
        self.assertEqual({k["owner"] for k in kids} | {self.fk.row("Task", parent)["owner"]},
                         {F.GIVER})


if __name__ == "__main__":
    unittest.main()

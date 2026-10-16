# -*- coding: utf-8 -*-
"""PM redesign - integration gaps closed by the BE/FE reconcile pass (16/10/2026), fake frappe.

  2a tasks.get: can_manage / is_leader / recurrence / history
  2b PM Task Seen write is committed (durable on GET) and never breaks tasks.get
  2c pm_inbox.request_deadline returns {request: <name>}
  2d assignment.create_with_task: review_required / auto_close / recipients + split_per_assignee
  2e PM Recurrence completion flags (p028): stored, copied by create_from_task, applied by _clone
  +  coordinate to-do shapes the PMR screen reads (late person, aggregated unassigned / nodue)

Run:  cd src && python3 -m unittest discover -s ecentric_workspace/pm/tests/standalone -p 'test_*.py'
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
        self.tasks = self.fk.load("ecentric_workspace.pm.api.tasks")
        self.inbox = self.fk.load("ecentric_workspace.pm.api.pm_inbox")
        self.asg = self.fk.load("ecentric_workspace.pm.api.assignment")
        self.rec = self.fk.load("ecentric_workspace.pm.api.recurrence")
        self.fk.hooks["PM Assignment Request"] = [self.asg.pm_assignment_request_guard]

        def _task_default_state(doc, method=None):  # what the PM Task Workflow does on insert
            if not doc.get("workflow_state"):
                doc["workflow_state"] = "Backlog"
        self.fk.hooks["Task"] = [_task_default_state]

    def as_user(self, u):
        self.fk.set_user(u)

    def state(self, name):
        return self.fk.row("Task", name)["workflow_state"]


# ------------------------------------------------------------------ 2a tasks.get extra fields
class TestTaskGetExtras(Base):
    def setUp(self):
        super(TestTaskGetExtras, self).setUp()
        F.task(self.fk, "T", owner=F.GIVER, assign=[F.ALICE])

    def test_can_manage_and_is_leader_per_role(self):
        self.as_user(F.GIVER)
        d = self.tasks.get("T")["task"]
        self.assertEqual((d["can_manage"], d["is_leader"]), (1, 0))
        self.as_user(F.LEADER)
        d = self.tasks.get("T")["task"]
        self.assertEqual((d["can_manage"], d["is_leader"]), (1, 1))
        self.as_user(F.ALICE)
        d = self.tasks.get("T")["task"]
        self.assertEqual((d["can_manage"], d["is_leader"]), (0, 0))

    def test_recurrence_label_or_null(self):
        self.as_user(F.ALICE)
        self.assertIsNone(self.tasks.get("T")["task"]["recurrence"])
        self.fk.add("PM Recurrence", name="REC-1", last_task="T", frequency="Monthly",
                    interval=1, monthly_day=7, weekly_days="[]", status="Active")
        rec = self.tasks.get("T")["task"]["recurrence"]
        self.assertEqual(rec["name"], "REC-1")
        self.assertIn("ngày 7", rec["label"])

    def test_history_lists_state_changes_newest_first(self):
        self.as_user(F.ALICE)
        self.tasks.set_status("T", "In Progress")
        self.fk.advance(minutes=5)
        self.tasks.mark_done("T")
        h = self.tasks.get("T")["task"]["history"]
        self.assertEqual([(x["from"], x["to"], x["by"], x["by_name"]) for x in h],
                         [("In Progress", "Done", F.ALICE, "Alice"),
                          ("To Do", "In Progress", F.ALICE, "Alice")])
        self.assertEqual(set(h[0]), {"at", "by", "by_name", "from", "to"})

    def test_history_capped_and_skips_unreadable_versions(self):
        for i in range(25):
            self.fk.add("Version", name="V%02d" % i, ref_doctype="Task", docname="T",
                        owner=F.GIVER, creation="2026-10-%02d 08:00:00" % (1 + i % 15),
                        data=json.dumps({"changed": [["workflow_state", "To Do", "Review"],
                                                     ["priority", "Low", "High"]]}))
        self.fk.add("Version", name="BAD", ref_doctype="Task", docname="T", owner=F.GIVER,
                    creation="2026-10-16 09:00:00", data="{not json")
        self.as_user(F.ALICE)
        h = self.tasks.get("T")["task"]["history"]
        self.assertEqual(len(h), self.fk.load("ecentric_workspace.pm.task_flow").HISTORY_LIMIT)
        self.assertTrue(all(x["to"] == "Review" for x in h))

    def test_history_never_breaks_get(self):
        tflow = self.fk.load("ecentric_workspace.pm.task_flow")
        orig = self.fk.module.get_all

        def boom(dt, *a, **k):
            if dt == "Version":
                raise RuntimeError("no Version table")
            return orig(dt, *a, **k)
        self.fk.module.get_all = boom
        try:
            self.as_user(F.ALICE)
            self.assertEqual(self.tasks.get("T")["task"]["history"], [])
            self.assertEqual(tflow.state_history("T"), [])
        finally:
            self.fk.module.get_all = orig

    def test_pending_request_carries_from_name_and_status(self):
        self.as_user(F.ALICE)
        self.inbox.request_deadline("T", "2026-11-30", "cho file")
        self.as_user(F.GIVER)
        p = self.tasks.get("T")["task"]["pending_deadline_request"]
        self.assertEqual((p["from_name"], p["status"], p["requested_by"]),
                         ("Alice", "Pending", F.ALICE))


# ------------------------------------------------------------------ 2b seen durable
class TestSeenCommit(Base):
    def setUp(self):
        super(TestSeenCommit, self).setUp()
        F.task(self.fk, "T", owner=F.GIVER, assign=[F.ALICE])
        self.commits = []
        self.fk.db.commit = lambda: self.commits.append(1)

    def test_assignee_open_commits_seen_row(self):
        self.as_user(F.ALICE)
        self.tasks.get("T")
        self.assertIsNotNone(self.fk.row("PM Task Seen", "T::" + F.ALICE))
        self.assertEqual(len(self.commits), 1)
        self.tasks.get("T")  # last_seen refresh is committed too
        self.assertEqual(len(self.commits), 2)

    def test_non_assignee_open_writes_and_commits_nothing(self):
        self.as_user(F.GIVER)
        self.tasks.get("T")
        self.assertEqual((len(self.fk.db.t("PM Task Seen")), len(self.commits)), (0, 0))

    def test_commit_failure_never_breaks_get(self):
        def boom():
            raise RuntimeError("commit failed")
        self.fk.db.commit = boom
        self.as_user(F.ALICE)
        out = self.tasks.get("T")
        self.assertEqual(out["task"]["name"], "T")
        self.assertTrue(self.fk.errors)


# ------------------------------------------------------------------ 2c request_deadline result
class TestRequestDeadlineResult(Base):
    def setUp(self):
        super(TestRequestDeadlineResult, self).setUp()
        F.task(self.fk, "T", owner=F.GIVER, assign=[F.ALICE], end="2026-10-20")

    def test_returns_request_name(self):
        self.as_user(F.ALICE)
        r = self.inbox.request_deadline("T", "2026-10-25", "cho so lieu")
        self.assertEqual(self.fk.row("PM Assignment Request", r["request"])["kind"], "Deadline")
        self.assertEqual((r["task"], r["status"], r["old_end"], r["new_end"]),
                         ("T", "Pending", "2026-10-20", "2026-10-25"))

    def test_non_assignee_denied(self):
        self.as_user(F.BOB)
        with self.assertRaises(F.PermissionError):
            self.inbox.request_deadline("T", "2026-10-25", "x")


# ------------------------------------------------------------------ 2d create_with_task split
class TestCreateWithTaskSplit(Base):
    def setUp(self):
        super(TestCreateWithTaskSplit, self).setUp()
        fk = self.fk

        def apply_workflow(doc, action):  # Backlog -> To Do on accept (governed in production)
            fk.db.set_value("Task", doc.name, "workflow_state", "To Do")
        self.asg.apply_workflow = apply_workflow

    def test_single_recipient_result_unchanged_and_flags_stored(self):
        self.as_user(F.GIVER)
        r = self.asg.create_with_task("Bao cao", recipient=F.ALICE, review_required=1)
        self.assertEqual(set(r), {"task", "request"})
        row = self.fk.row("Task", r["task"])
        self.assertEqual((row["ec_review_required"], row["ec_auto_close"],
                          json.loads(row.get("_assign") or "[]")), (1, 0, []))
        self.assertEqual(r["request"]["recipient"], F.ALICE)

    def test_split_each_recipient_gets_child_and_request(self):
        self.as_user(F.GIVER)
        r = self.asg.create_with_task("Bao cao", recipients=json.dumps([F.ALICE, F.BOB]),
                                      split_per_assignee=1, auto_close=1, review_required=0,
                                      proposed_end="2026-10-30 18:00:00")
        self.assertEqual(set(r), {"task", "children", "requests", "split"})
        parent = self.fk.row("Task", r["task"])
        self.assertEqual((parent["ec_split_parent"], parent["ec_auto_close"], parent["is_group"],
                          json.loads(parent["_assign"])), (1, 1, 1, [F.GIVER]))
        self.assertEqual(len(r["children"]), 2)
        for child, req, who in zip(r["children"], r["requests"], (F.ALICE, F.BOB)):
            c = self.fk.row("Task", child)
            self.assertEqual((c["parent_task"], json.loads(c.get("_assign") or "[]")),
                             (r["task"], []))
            self.assertEqual((req["task"], req["recipient"], req["status"]), (child, who, "Pending"))
        self.assertEqual(self.fk.row("Task", r["children"][0])["subject"], "Bao cao — Alice")
        # each recipient sees their own request in "Được giao cho tôi"
        self.as_user(F.BOB)
        self.assertEqual([x["task"] for x in self.inbox.received()["needs_reply"]],
                         [r["children"][1]])

    def test_one_rejection_cancels_only_that_child_and_tells_giver(self):
        self.as_user(F.GIVER)
        r = self.asg.create_with_task("Bao cao", recipients=[F.ALICE, F.BOB],
                                      split_per_assignee=1)
        ca, cb = r["children"]
        ra, rb = [x["name"] for x in r["requests"]]
        self.as_user(F.BOB)
        self.asg.respond(rb, "reject", reason="dang nghi phep")
        self.assertEqual(self.state(cb), "Cancelled")
        self.assertNotIn(self.state(r["task"]), ("Done", "Cancelled", "Review"))
        told = [n for n in self.fk.notifications if n["user"] == F.GIVER and n["task"] == r["task"]]
        self.assertTrue(told and "từ chối" in told[-1]["subject"])
        # Alice accepts and finishes -> the parent rolls up without Bob (auto_close=0 -> Review)
        self.as_user(F.ALICE)
        self.asg.respond(ra, "accept")
        self.assertEqual(json.loads(self.fk.row("Task", ca)["_assign"]), [F.ALICE])
        self.assertEqual(self.tasks.mark_done(ca)["state"], "Done")
        self.assertEqual(self.state(r["task"]), "Review")

    def test_multiple_recipients_without_split_still_rejected(self):
        self.as_user(F.GIVER)
        with self.assertRaises(F.ValidationError):
            self.asg.create_with_task("Bao cao", recipients=[F.ALICE, F.BOB])
        self.assertEqual(len(self.fk.db.t("Task")), 0)

    def test_split_invalid_recipient_writes_nothing(self):
        self.fk.add("User", name="off@ec.vn", full_name="Off", enabled=0, user_type="System User")
        self.as_user(F.GIVER)
        with self.assertRaises(F.ValidationError):
            self.asg.create_with_task("Bao cao", recipients=[F.ALICE, "off@ec.vn"],
                                      split_per_assignee=1)
        self.assertEqual((len(self.fk.db.t("Task")), len(self.fk.db.t("PM Assignment Request"))),
                         (0, 0))


# ------------------------------------------------------------------ 2e recurrence flags
class TestRecurrenceFlags(Base):
    def test_create_stores_and_returns_flags(self):
        self.as_user(F.GIVER)
        r = self.rec.create("Bao cao", "Daily", assignees=[F.ALICE, F.BOB],
                            split_per_assignee=1, auto_close="1", review_required=0)
        row = self.fk.row("PM Recurrence", r["name"])
        self.assertEqual((row["split_per_assignee"], row["auto_close"], row["review_required"]),
                         (1, 1, 0))
        self.assertEqual((r["split_per_assignee"], r["auto_close"], r["review_required"]),
                         (1, 1, 0))
        plain = self.rec.create("Mot minh", "Daily")
        self.assertEqual((plain["split_per_assignee"], plain["auto_close"],
                          plain["review_required"]), (0, 0, 0))

    def test_update_template_changes_only_supplied_flags(self):
        self.as_user(F.GIVER)
        r = self.rec.create("Bao cao", "Daily", review_required=1)
        out = self.rec.update_template(r["name"], auto_close=1)
        self.assertEqual((out["auto_close"], out["review_required"]), (1, 1))

    def test_create_from_split_task_copies_flags_and_people(self):
        self.as_user(F.GIVER)
        t = self.tasks.create("", "Bao cao", assignees=[F.ALICE, F.BOB], split_per_assignee=1,
                              auto_close=1, review_required=1, exp_end_date="2026-10-20")
        r = self.rec.create_from_task(t["name"], "Monthly", monthly_day=20)
        self.assertEqual((r["split_per_assignee"], r["auto_close"], r["review_required"]),
                         (1, 1, 1))
        self.assertEqual(r["assignees"], [F.ALICE, F.BOB])  # from the children, not the parent
        self.assertEqual(r["subtasks"], [])                # children are not template sub-tasks
        self.assertEqual(self.fk.row("PM Recurrence", r["name"])["last_task"], t["name"])
        self.assertEqual(self.tasks.get(t["name"])["task"]["recurrence"]["name"], r["name"])

    def test_create_from_request_task_uses_pending_recipient(self):
        self.as_user(F.GIVER)
        made = self.asg.create_with_task("Bao cao", recipient=F.ALICE, review_required=1)
        r = self.rec.create_from_task(made["task"], "Daily")
        self.assertEqual((r["assignees"], r["review_required"], r["split_per_assignee"]),
                         ([F.ALICE], 1, 0))

    def test_occurrence_applies_split_auto_close_review(self):
        self.as_user(F.GIVER)
        r = self.rec.create("Bao cao", "Daily", assignees=[F.ALICE, F.BOB],
                            split_per_assignee=1, auto_close=1, review_required=1,
                            checklist_items=json.dumps(["Keo so"]), start_date="2026-10-16",
                            subtasks=json.dumps([{"subject": "khong duoc tao"}]))
        self.as_user("Administrator")
        self.rec._process(r["name"], self.fk.utils.getdate("2026-10-16"))
        rule = self.fk.row("PM Recurrence", r["name"])
        parent = self.fk.row("Task", rule["last_task"])
        self.assertEqual((parent["ec_split_parent"], parent["ec_auto_close"],
                          parent["ec_review_required"], json.loads(parent["_assign"])),
                         (1, 1, 1, [F.GIVER]))
        self.assertFalse(parent.get("pm_checklist"))
        kids = [t for t in self.fk.db.t("Task").values() if t.get("parent_task") == parent["name"]]
        self.assertEqual(sorted(json.loads(k["_assign"])[0] for k in kids), [F.ALICE, F.BOB])
        self.assertTrue(all(k["ec_review_required"] == 1 for k in kids))
        self.assertTrue(all([c["item_label"] for c in k["pm_checklist"]] == ["Keo so"] for k in kids))
        # BUGFIX regression: _process advanced the schedule (no TypeError -> no rollback)
        self.assertEqual((rule["occurrences_done"], str(rule["next_run_date"])), (1, "2026-10-17"))
        # a recurring split child resolves its giver through the parent's rule
        self.as_user(F.ALICE)
        mine = [k for k in kids if F.ALICE in k["_assign"]][0]
        self.assertEqual(self.tasks.get(mine["name"])["task"]["giver"]["user"], F.GIVER)
        # each person finishes their part -> last child Done -> auto_close parent Done
        for k in kids:
            self.fk.row("Task", k["name"])["pm_checklist"] = []  # steps are not required here
            self.as_user(json.loads(k["_assign"])[0])
            self.fk.row("Task", k["name"])["ec_review_required"] = 0
            self.assertEqual(self.tasks.mark_done(k["name"])["state"], "Done")
        self.assertEqual(self.state(parent["name"]), "Done")

    def test_occurrence_without_flags_unchanged(self):
        self.as_user(F.GIVER)
        r = self.rec.create("Mot minh", "Daily", assignees=[F.ALICE, F.BOB],
                            start_date="2026-10-16")
        self.as_user("Administrator")
        self.rec._process(r["name"], self.fk.utils.getdate("2026-10-16"))
        t = self.fk.row("Task", self.fk.row("PM Recurrence", r["name"])["last_task"])
        self.assertEqual((t.get("ec_split_parent"), t["ec_review_required"],
                          sorted(json.loads(t["_assign"]))), (None, 0, [F.ALICE, F.BOB]))

    def test_create_from_subtask_and_outsider_rejected(self):
        F.task(self.fk, "P", owner=F.GIVER, assign=[F.GIVER], is_group=1)
        F.task(self.fk, "C", owner=F.GIVER, assign=[F.ALICE], parent_task="P")
        self.as_user(F.GIVER)
        with self.assertRaises(F.ValidationError):
            self.rec.create_from_task("C", "Daily")
        self.fk.add("Project", name="P9", project_name="Kin")
        F.task(self.fk, "X", owner=F.GIVER, assign=[F.ALICE], project="P9")
        self.as_user(F.OUTSIDER)
        with self.assertRaises(F.PermissionError):
            self.rec.create_from_task("X", "Daily")

    def test_p028_adds_fields_once_and_is_registered(self):
        p = self.fk.load("ecentric_workspace.pm.patches.p028_pm_recurrence_completion_flags")
        self.fk.doctypes.update({"Custom Field", "PM Recurrence"})
        p.execute()
        made = sorted((r["dt"], r["fieldname"]) for r in self.fk.db.t("Custom Field").values())
        self.assertEqual(made, [("PM Recurrence", "auto_close"),
                                ("PM Recurrence", "review_required"),
                                ("PM Recurrence", "split_per_assignee")])
        for r in list(self.fk.db.t("Custom Field").values()):  # name as Frappe names them
            self.fk.db.t("Custom Field")["PM Recurrence-" + r["fieldname"]] = r
        p.execute()
        self.assertEqual(len({r["fieldname"] for r in self.fk.db.t("Custom Field").values()}), 3)
        with open(os.path.join(F.SRC, "ecentric_workspace", "patches.txt"), encoding="utf-8") as fh:
            lines = [l.strip() for l in fh]
        self.assertGreater(lines.index("ecentric_workspace.pm.patches.p028_pm_recurrence_completion_flags"),
                           lines.index("ecentric_workspace.pm.patches.p027_pm_task_seen_baseline"))

    def test_p028_missing_doctype_is_logged_not_raised(self):
        p = self.fk.load("ecentric_workspace.pm.patches.p028_pm_recurrence_completion_flags")
        p.execute()  # "PM Recurrence" not in fk.doctypes
        self.assertEqual(len(self.fk.db.t("Custom Field")), 0)
        self.assertTrue(self.fk.errors)


# ------------------------------------------------------------------ coordinate to-do shapes
class TestCoordinateTodoShapes(Base):
    def setUp(self):
        super(TestCoordinateTodoShapes, self).setUp()
        self.fk.add("Project", name="P1", project_name="Du an 1", ec_manager=F.GIVER)
        self.fk.add("Project", name="WL", project_name="ERP - log", ec_personal_log=1)
        F.task(self.fk, "LATE", assign=[F.ALICE], project="P1", end="2026-10-10")
        F.task(self.fk, "FREE1", assign=[], project="P1")
        F.task(self.fk, "FREE2", assign=[], project="P1")
        F.task(self.fk, "FREE3", assign=[])

    def test_late_row_names_the_person_and_opened(self):
        self.as_user(F.LEADER)
        late = [x for x in self.inbox.coordinate()["todo"] if x["kind"] == "late"][0]
        self.assertEqual((late["user"], late["full_name"], late["opened"], late["days_late"]),
                         (F.ALICE, "Alice", False, 6))
        self.fk.add("PM Task Seen", name="LATE::" + F.ALICE, task="LATE", user=F.ALICE,
                    first_seen="2026-10-11 08:00:00", last_seen="2026-10-11 08:00:00")
        late = [x for x in self.inbox.coordinate()["todo"] if x["kind"] == "late"][0]
        self.assertTrue(late["opened"])

    def test_unassigned_is_one_aggregated_row(self):
        self.as_user(F.LEADER)
        r = self.inbox.coordinate()
        un = [x for x in r["todo"] if x["kind"] == "unassigned"]
        self.assertEqual(len(un), 1)
        self.assertEqual(un[0]["count"], 3)
        self.assertEqual(un[0]["projects"][0], {"project": "P1", "project_name": "Du an 1",
                                                "count": 2})
        self.assertEqual(r["personal_hidden"], 1)
        self.assertEqual(r["projects"][0]["owner_name"], "Gia Ver")
        self.assertEqual(self.inbox.coordinate(include_personal=1)["personal_hidden"], 0)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""BE <-> FE CONTRACT for the /pm redesign: exact key sets returned by the endpoints that
window.PMR (public/js/pm/pm_redesign.js) reads.

Two-sided drift guard:
  * this file runs the REAL backend functions under the fake frappe and asserts their key sets
    equal CONTRACT below (exact; entries ending in "+" are a required SUBSET of a larger dict,
    e.g. tasks.get `task` also carries every Task column);
  * public/js/pm/tests/pm_redesign.test.js holds the SAME table between `// CONTRACT-BEGIN` and
    `// CONTRACT-END`; test_js_contract_table_matches parses it and requires equality, and the JS
    test requires every fake-api fixture PMR is tested against to stay within that table.
So: change a backend shape -> update CONTRACT here AND in the JS file, or a test fails.

Run:  cd src && python3 -m unittest discover -s ecentric_workspace/pm/tests/standalone -p 'test_*.py'
"""
import io
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402

JS_TEST = os.path.join(F.SRC, "ecentric_workspace", "public", "js", "pm", "tests",
                       "pm_redesign.test.js")

PERSON = ["done_on", "full_name", "late", "opened", "state", "steps", "task", "user"]
CONTRACT = {
    "tasks.get": ["subtasks", "task", "user_names"],
    "tasks.get.task+": ["auto_close", "can_edit", "can_manage", "children_progress", "giver", "history",
                        "is_leader", "pending_deadline_request", "recurrence", "review_required",
                        "split"],
    "tasks.get.giver": ["full_name", "user"],
    "tasks.get.recurrence": ["label", "name"],
    "tasks.get.pending_deadline_request": ["created", "from_name", "new_end", "reason",
                                           "recipient", "request", "requested_by", "status"],
    "tasks.get.children_progress": ["done", "open", "people", "total"],
    "tasks.get.history": ["at", "by", "by_name", "from", "to"],
    "person": PERSON,
    "tasks.mark_done": ["blocked_reason", "missing", "parent_state", "state", "withdrew_request"],
    "tasks.create": ["name", "parent_task", "project", "subject"],
    "tasks.create.split": ["children", "name", "parent_task", "project", "split", "subject"],
    "pm_inbox.received": ["badge", "my_deadline_requests", "needs_reply", "unopened"],
    "pm_inbox.received.needs_reply": ["created", "from_name", "from_user", "message",
                                      "project_name", "proposed_end", "request", "subject",
                                      "task"],
    "pm_inbox.received.unopened": ["exp_end_date", "from_name", "from_user", "project_name",
                                   "subject", "task", "workflow_state"],
    "pm_inbox.received.my_deadline_requests": ["answer", "answered_at", "new_end", "old_end",
                                               "reason", "request", "status", "subject", "task",
                                               "unseen"],
    "pm_inbox.given": ["banner", "batches", "rules"],
    "pm_inbox.given.banner": ["created", "from_name", "from_user", "new_end", "old_end",
                              "project_name", "reason", "request", "subject", "task"],
    "pm_inbox.given.batches": ["auto_close", "done_count", "exp_end_date", "people",
                               "project_name", "recurrence", "review_required", "split",
                               "subject", "task", "total", "workflow_state"],
    "pm_inbox.given.rules": ["assignees", "name", "next_run", "schedule_label", "status",
                             "subject"],
    "pm_inbox.coordinate": ["kpi", "people", "personal_hidden", "projects", "todo"],
    "pm_inbox.coordinate.kpi": ["done_week", "late", "on_time_pct_30d", "open", "unassigned"],
    "pm_inbox.coordinate.todo.late": ["assignees", "days_late", "exp_end_date", "full_name",
                                      "kind", "opened", "project", "project_name", "subject",
                                      "task", "user", "workflow_state"],
    "pm_inbox.coordinate.todo.group": ["count", "kind", "projects", "tasks"],
    "pm_inbox.coordinate.todo.overload": ["full_name", "kind", "late", "open", "user"],
    "pm_inbox.coordinate.people": ["done_week", "full_name", "late", "open", "user"],
    "pm_inbox.coordinate.projects": ["done", "late", "name", "open", "owner", "owner_name",
                                     "project_name", "total", "unassigned"],
    "pm_inbox.request_deadline": ["new_end", "old_end", "request", "status", "task"],
    "pm_inbox.answer_deadline": ["exp_end_date", "parent_extended", "request", "status", "task"],
    "pm_inbox.withdraw_deadline": ["request", "status"],
    "pm_inbox.nudge": ["sent", "skipped", "task"],
    "pm_inbox.close_parent": ["returned", "state", "task"],
    "dashboard.rail_badges": ["assignments", "mywork", "received"],
    "assignment.create_with_task": ["request", "task"],
    "assignment.create_with_task.split": ["children", "requests", "split", "task"],
    "recurrence.create_from_task+": ["auto_close", "name", "review_required",
                                     "split_per_assignee"],
}


def js_contract():
    with io.open(JS_TEST, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"// CONTRACT-BEGIN[^\n]*\nconst CONTRACT = (\{.*?\});\n// CONTRACT-END", src, re.S)
    if not m:
        raise AssertionError("CONTRACT block not found in " + JS_TEST)
    return json.loads(m.group(1))


class Base(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.tasks = self.fk.load("ecentric_workspace.pm.api.tasks")
        self.inbox = self.fk.load("ecentric_workspace.pm.api.pm_inbox")
        self.asg = self.fk.load("ecentric_workspace.pm.api.assignment")
        self.rec = self.fk.load("ecentric_workspace.pm.api.recurrence")
        self.dash = self.fk.load("ecentric_workspace.pm.api.dashboard")
        self.fk.hooks["PM Assignment Request"] = [self.asg.pm_assignment_request_guard]

        def _task_default_state(doc, method=None):
            if not doc.get("workflow_state"):
                doc["workflow_state"] = "Backlog"
        self.fk.hooks["Task"] = [_task_default_state]
        fk = self.fk
        self.asg.apply_workflow = lambda doc, action: fk.db.set_value(
            "Task", doc.name, "workflow_state", "To Do")
        self.fk.add("Project", name="P1", project_name="Du an 1", ec_manager=F.GIVER,
                    expected_end_date="2026-12-31")

    def as_user(self, u):
        self.fk.set_user(u)

    def keys(self, name, obj):
        want = CONTRACT[name]
        if name.endswith("+"):
            missing = set(want) - set(obj)
            self.assertFalse(missing, "%s missing %s" % (name, sorted(missing)))
        else:
            self.assertEqual(sorted(obj), want, name)


class TestContractTable(unittest.TestCase):
    def test_js_contract_table_matches(self):
        self.assertEqual(js_contract(), CONTRACT)


class TestTaskShapes(Base):
    def test_tasks_get(self):
        F.task(self.fk, "SP", owner=F.GIVER, assign=[F.GIVER], is_group=1, split=1, project="P1",
               end="2026-10-20")
        F.task(self.fk, "SP-A", owner=F.GIVER, assign=[F.ALICE], parent_task="SP", project="P1",
               end="2026-10-20")
        F.task(self.fk, "SP-B", owner=F.GIVER, assign=[F.BOB], parent_task="SP", project="P1",
               end="2026-10-20")
        self.fk.add("PM Recurrence", name="REC-1", last_task="SP", frequency="Daily", interval=1,
                    weekly_days="[]", status="Active")
        self.as_user(F.ALICE)
        self.inbox.request_deadline("SP-A", "2026-10-19", "ly do")
        self.tasks.set_status("SP-A", "In Progress")
        self.as_user(F.GIVER)
        out = self.tasks.get("SP")
        self.keys("tasks.get", out)
        t = out["task"]
        self.keys("tasks.get.task+", t)
        self.keys("tasks.get.giver", t["giver"])
        self.keys("tasks.get.recurrence", t["recurrence"])
        self.keys("tasks.get.children_progress", t["children_progress"])
        for p in t["children_progress"]["people"]:
            self.keys("person", p)
        child = self.tasks.get("SP-A")["task"]
        self.keys("tasks.get.pending_deadline_request", child["pending_deadline_request"])
        self.assertTrue(child["history"])
        for h in child["history"]:
            self.keys("tasks.get.history", h)

    def test_mark_done_scenarios(self):
        allowed = set(CONTRACT["tasks.mark_done"])
        F.task(self.fk, "T", owner=F.GIVER, assign=[F.ALICE])
        F.task(self.fk, "B", owner=F.GIVER, assign=[F.ALICE],
               pm_checklist=[{"item_label": "a", "is_required": 1, "is_done": 0}])
        F.task(self.fk, "W", owner=F.GIVER, assign=[F.ALICE], end="2026-10-20")
        F.task(self.fk, "SP", owner=F.GIVER, assign=[F.GIVER], is_group=1, split=1)
        F.task(self.fk, "SP-A", owner=F.GIVER, assign=[F.ALICE], parent_task="SP")
        self.as_user(F.ALICE)
        self.inbox.request_deadline("W", "2026-10-25", "x")
        cases = [(self.tasks.mark_done("T"), {"state"}),
                 (self.tasks.mark_done("B"), {"state", "blocked_reason", "missing"}),
                 (self.tasks.mark_done("W"), {"state", "withdrew_request"}),
                 (self.tasks.mark_done("SP-A"), {"state", "parent_state"})]
        for out, want in cases:
            self.assertEqual(set(out), want)
            self.assertTrue(set(out) <= allowed)

    def test_tasks_create(self):
        self.as_user(F.GIVER)
        self.keys("tasks.create", self.tasks.create("", "Mot", assignee=F.ALICE))
        self.keys("tasks.create.split", self.tasks.create("", "Hai", assignees=[F.ALICE, F.BOB],
                                                          split_per_assignee=1))


class TestInboxShapes(Base):
    def test_received(self):
        F.task(self.fk, "U", owner=F.GIVER, assign=[F.ALICE], project="P1", end="2026-10-30")
        F.task(self.fk, "D", owner=F.GIVER, assign=[F.ALICE], project="P1", end="2026-10-30")
        self.as_user(F.GIVER)
        self.asg.create_with_task("Can dong y", recipient=F.ALICE)
        self.as_user(F.ALICE)
        self.inbox.request_deadline("D", "2026-11-05", "x")
        out = self.inbox.received()
        self.keys("pm_inbox.received", out)
        for k, sub in (("needs_reply", "needs_reply"), ("unopened", "unopened"),
                       ("my_deadline_requests", "my_deadline_requests")):
            self.assertTrue(out[k], k)
            for row in out[k]:
                self.keys("pm_inbox.received." + sub, row)
        self.keys("dashboard.rail_badges", self.dash.rail_badges())

    def test_given_run_and_rep(self):
        self.as_user(F.GIVER)
        made = self.tasks.create("P1", "Bao cao", assignees=[F.ALICE, F.BOB], split_per_assignee=1,
                                 exp_end_date="2026-10-30")
        self.rec.create("Lap", "Daily", assignees=[F.ALICE])
        self.as_user(F.ALICE)
        self.inbox.request_deadline(made["children"][0], "2026-11-02", "x")
        self.as_user(F.GIVER)
        out = self.inbox.given("run")
        self.keys("pm_inbox.given", out)
        self.keys("pm_inbox.given.banner", out["banner"][0])
        self.keys("pm_inbox.given.batches", out["batches"][0])
        for p in out["batches"][0]["people"]:
            self.keys("person", p)
        rep = self.inbox.given("rep")
        self.keys("pm_inbox.given", rep)
        self.keys("pm_inbox.given.rules", rep["rules"][0])

    def test_coordinate(self):
        F.task(self.fk, "LATE", assign=[F.ALICE], project="P1", end="2026-10-01")
        F.task(self.fk, "FREE", assign=[], project="P1")
        F.task(self.fk, "NODUE", assign=[F.BOB], project="P1", creation="2026-10-01 08:00:00")
        for i in range(6):
            F.task(self.fk, "BUSY%d" % i, assign=[F.BOB], project="P1", end="2026-10-30")
        for u in (F.GIVER, F.OUTSIDER):  # team median stays low -> Bob is "overload"
            F.task(self.fk, "ONE-" + u, assign=[u], project="P1", end="2026-10-30")
        self.as_user(F.LEADER)
        out = self.inbox.coordinate()
        self.keys("pm_inbox.coordinate", out)
        self.keys("pm_inbox.coordinate.kpi", out["kpi"])
        kinds = {}
        for x in out["todo"]:
            kinds.setdefault(x["kind"], x)
        self.assertEqual(sorted(kinds), ["late", "nodue", "overload", "unassigned"])
        self.keys("pm_inbox.coordinate.todo.late", kinds["late"])
        self.keys("pm_inbox.coordinate.todo.group", kinds["unassigned"])
        self.keys("pm_inbox.coordinate.todo.group", kinds["nodue"])
        self.keys("pm_inbox.coordinate.todo.overload", kinds["overload"])
        self.keys("pm_inbox.coordinate.people", out["people"][0])
        self.keys("pm_inbox.coordinate.projects", out["projects"][0])

    def test_deadline_nudge_close(self):
        F.task(self.fk, "T", owner=F.GIVER, assign=[F.ALICE], project="P1", end="2026-10-20")
        F.task(self.fk, "T2", owner=F.GIVER, assign=[F.ALICE], project="P1", end="2026-10-20")
        self.as_user(F.ALICE)
        r = self.inbox.request_deadline("T", "2026-10-25", "x")
        self.keys("pm_inbox.request_deadline", r)
        r2 = self.inbox.request_deadline("T2", "2026-10-26", "y")
        self.keys("pm_inbox.withdraw_deadline", self.inbox.withdraw_deadline(r2["request"]))
        self.as_user(F.GIVER)
        self.keys("pm_inbox.answer_deadline", self.inbox.answer_deadline(r["request"], 1))
        self.keys("pm_inbox.nudge", self.inbox.nudge("T"))
        self.keys("pm_inbox.close_parent", self.inbox.close_parent("T2", return_users=[F.ALICE]))
        self.keys("pm_inbox.close_parent", self.inbox.close_parent("T"))


class TestCreateShapes(Base):
    def test_create_with_task_and_recurrence(self):
        self.as_user(F.GIVER)
        single = self.asg.create_with_task("Mot", recipient=F.ALICE)
        self.keys("assignment.create_with_task", single)
        split = self.asg.create_with_task("Hai", recipients=[F.ALICE, F.BOB], split_per_assignee=1)
        self.keys("assignment.create_with_task.split", split)
        self.keys("recurrence.create_from_task+", self.rec.create_from_task(split["task"], "Daily"))


if __name__ == "__main__":
    unittest.main()

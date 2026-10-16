# -*- coding: utf-8 -*-
"""PM redesign BE - tasks.mark_done / set_status / create / get / list, projects.list,
dashboard, assignment split-reject, events registry, patches (fake frappe, no bench).

Run:  cd src && python3 -m unittest discover -s ecentric_workspace/pm/tests/standalone -p 'test_redesign_*.py'
"""
import ast
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402

APP = os.path.join(F.SRC, "ecentric_workspace")


class Base(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.tasks = self.fk.load("ecentric_workspace.pm.api.tasks")
        self.asg = self.fk.load("ecentric_workspace.pm.api.assignment")
        self.fk.hooks["PM Assignment Request"] = [self.asg.pm_assignment_request_guard]

    def as_user(self, u):
        self.fk.set_user(u)

    def state(self, name):
        return self.fk.row("Task", name)["workflow_state"]

    def events(self, event_type):
        return [n for n in self.fk.notifications if n["event_type"] == event_type]


# ------------------------------------------------------------------ mark_done
class TestMarkDone(Base):
    def test_done_writes_completed_on_and_version(self):
        F.task(self.fk, "T", assign=[F.ALICE])
        self.as_user(F.ALICE)
        out = self.tasks.mark_done("T")
        self.assertEqual(out, {"state": "Done"})
        row = self.fk.row("Task", "T")
        self.assertEqual((row["workflow_state"], row["status"], row["completed_on"],
                          row["completed_by"]), ("Done", "Completed", "2026-10-16", F.ALICE))
        versions = [r for r in self.fk.db.t("Version").values() if r["docname"] == "T"]
        self.assertEqual(json.loads(versions[0]["data"])["changed"][0], ["workflow_state", "To Do", "Done"])

    def test_blocked_required_steps_is_not_an_error(self):
        F.task(self.fk, "T", assign=[F.ALICE],
               pm_checklist=[{"item_label": "a", "is_required": 1, "is_done": 0},
                             {"item_label": "b", "is_required": 0, "is_done": 0}])
        self.as_user(F.ALICE)
        out = self.tasks.mark_done("T")
        self.assertEqual(out, {"state": "To Do", "blocked_reason": "required_steps", "missing": 1})
        self.assertEqual(self.state("T"), "To Do")

    def test_blocked_open_children(self):
        F.task(self.fk, "P", assign=[F.GIVER], is_group=1)
        F.task(self.fk, "C", assign=[F.ALICE], parent_task="P")
        self.as_user(F.GIVER)
        out = self.tasks.mark_done("P")
        self.assertEqual(out["blocked_reason"], "open_children")
        self.assertEqual(self.state("P"), "To Do")

    def test_review_required_non_giver_goes_to_review(self):
        F.task(self.fk, "T", assign=[F.ALICE], review=1, subject="Bao cao")
        self.as_user(F.ALICE)
        out = self.tasks.mark_done("T")
        self.assertEqual(out["state"], "Review")
        self.assertEqual(self.state("T"), "Review")
        self.assertIsNone(self.fk.row("Task", "T").get("completed_on"))
        ev = self.events("task_ready_for_review")
        self.assertEqual([e["user"] for e in ev], [F.GIVER])
        self.as_user(F.GIVER)  # the giver closes it
        self.assertEqual(self.tasks.mark_done("T")["state"], "Done")

    def test_withdraws_pending_deadline_request(self):
        F.task(self.fk, "T", assign=[F.ALICE], end="2026-10-20")
        inbox = self.fk.load("ecentric_workspace.pm.api.pm_inbox")
        self.as_user(F.ALICE)
        req = inbox.request_deadline("T", "2026-10-25", "x")["request"]
        out = self.tasks.mark_done("T")
        self.assertEqual(out["withdrew_request"], req)
        self.assertEqual(self.fk.row("PM Assignment Request", req)["status"], "Cancelled")

    def test_permission_and_cancelled(self):
        self.fk.add("Project", name="P9", project_name="Kin")
        F.task(self.fk, "T", owner=F.GIVER, assign=[F.ALICE], project="P9")
        self.as_user(F.OUTSIDER)
        with self.assertRaises(F.PermissionError):
            self.tasks.mark_done("T")
        F.task(self.fk, "X", assign=[F.ALICE], state="Cancelled")
        self.as_user(F.ALICE)
        with self.assertRaises(F.ValidationError):
            self.tasks.mark_done("X")
        self.as_user("nopm@ec.vn")
        with self.assertRaises(F.PermissionError):
            self.tasks.mark_done("T")


# ------------------------------------------------------------------ set_status + roll-up
class TestSetStatusRollup(Base):
    def setUp(self):
        super(TestSetStatusRollup, self).setUp()
        F.task(self.fk, "SP", owner=F.GIVER, assign=[F.GIVER], is_group=1, split=1,
               subject="Bao cao thang")
        F.task(self.fk, "SP-A", owner=F.GIVER, assign=[F.ALICE], parent_task="SP")
        F.task(self.fk, "SP-B", owner=F.GIVER, assign=[F.BOB], parent_task="SP")

    def test_last_child_done_moves_parent_to_review_and_tells_giver(self):
        self.as_user(F.ALICE)
        self.tasks.set_status("SP-A", "Done")
        self.assertEqual(self.state("SP"), "To Do")
        self.as_user(F.BOB)
        out = self.tasks.mark_done("SP-B")
        self.assertEqual(out["parent_state"], "Review")
        self.assertEqual(self.state("SP"), "Review")
        ev = self.events("task_ready_for_review")
        self.assertEqual((ev[0]["user"], ev[0]["task"]), (F.GIVER, "SP"))
        self.assertTrue(any(c[1] == "SP" and "2/2" in c[3] for c in self.fk.comments))

    def test_auto_close_parent_goes_done(self):
        self.fk.row("Task", "SP")["ec_auto_close"] = 1
        self.as_user(F.ALICE)
        self.tasks.mark_done("SP-A")
        self.as_user(F.BOB)
        self.tasks.mark_done("SP-B")
        self.assertEqual(self.state("SP"), "Done")
        self.assertEqual(self.fk.row("Task", "SP")["completed_on"], "2026-10-16")
        self.assertEqual(self.events("task_ready_for_review"), [])

    def test_non_split_parent_untouched(self):
        self.fk.row("Task", "SP")["ec_split_parent"] = 0
        self.as_user(F.ALICE)
        self.tasks.mark_done("SP-A")
        self.as_user(F.BOB)
        self.tasks.mark_done("SP-B")
        self.assertEqual(self.state("SP"), "To Do")

    def test_leaving_done_clears_completed_on(self):
        self.as_user(F.ALICE)
        self.tasks.set_status("SP-A", "Done")
        self.tasks.set_status("SP-A", "In Progress")
        row = self.fk.row("Task", "SP-A")
        self.assertIsNone(row["completed_on"])
        self.assertEqual(row["status"], "Open")

    def test_guards_kept(self):
        self.as_user(F.ALICE)
        with self.assertRaises(F.PermissionError):
            self.tasks.set_status("SP-A", "Cancelled")
        self.as_user(F.GIVER)
        with self.assertRaises(F.ValidationError):
            self.tasks.set_status("SP", "Done")  # open children
        F.task(self.fk, "RV", assign=[F.ALICE], review=1)
        self.as_user(F.ALICE)
        with self.assertRaises(F.PermissionError):
            self.tasks.set_status("RV", "Done")  # review-required: giver closes

    def test_split_reject_cancels_only_that_child(self):
        F.task(self.fk, "SP-C", owner=F.GIVER, assign=[], parent_task="SP", state="Backlog")
        self.fk.add("PM Assignment Request", name="AR", task="SP-C", recipient=F.OUTSIDER,
                    requested_by=F.GIVER, status="Pending", kind="Assignment",
                    open_task_key="SP-C", open_request_key="SP-C::" + F.OUTSIDER)
        self.as_user(F.ALICE)
        self.tasks.mark_done("SP-A")
        self.as_user(F.BOB)
        self.tasks.mark_done("SP-B")
        self.assertEqual(self.state("SP"), "To Do")  # SP-C still open
        self.as_user(F.OUTSIDER)
        self.asg.respond("AR", "reject", reason="ban qua")
        self.assertEqual(self.state("SP-C"), "Cancelled")
        self.assertEqual(self.state("SP"), "Review")


# ------------------------------------------------------------------ create / get
class TestCreateGet(Base):
    def test_create_stores_flags_and_marks_split_parent(self):
        self.as_user(F.GIVER)
        r = self.tasks.create("", "Bao cao", assignees=[F.ALICE, F.BOB], split_per_assignee=1,
                              auto_close=1, review_required="1")
        parent = self.fk.row("Task", r["name"])
        self.assertEqual((parent["ec_split_parent"], parent["ec_auto_close"],
                          parent["ec_review_required"]), (1, 1, 1))
        kids = [self.fk.row("Task", c) for c in r["children"]]
        self.assertTrue(all(k["ec_review_required"] == 1 for k in kids))
        single = self.tasks.create("", "Mot minh", assignee=F.ALICE)
        row = self.fk.row("Task", single["name"])
        self.assertEqual((row["ec_auto_close"], row["ec_review_required"]), (0, 0))

    def test_create_old_signature_still_validates(self):
        self.as_user(F.GIVER)
        with self.assertRaises(F.ValidationError):
            self.tasks.create("", "")

    def test_get_returns_redesign_fields_and_records_seen(self):
        F.task(self.fk, "SP", owner=F.GIVER, assign=[F.GIVER], is_group=1, split=1, review=1,
               auto_close=1)
        F.task(self.fk, "SP-A", owner=F.GIVER, assign=[F.ALICE], parent_task="SP", state="Done")
        F.task(self.fk, "SP-B", owner=F.GIVER, assign=[F.BOB], parent_task="SP")
        self.as_user(F.GIVER)
        d = self.tasks.get("SP")["task"]
        self.assertEqual(d["giver"], {"user": F.GIVER, "full_name": "Gia Ver"})
        self.assertEqual((d["review_required"], d["auto_close"]), (1, 1))
        cp = d["children_progress"]
        self.assertEqual((cp["done"], cp["total"], cp["open"]), (1, 2, 1))
        self.assertEqual([(p["user"], p["task"], p["state"]) for p in cp["people"]],
                         [(F.ALICE, "SP-A", "Done"), (F.BOB, "SP-B", "To Do")])
        self.assertIsNone(d["pending_deadline_request"])
        self.assertIsNone(self.fk.row("PM Task Seen", "SP::" + F.ALICE))
        self.as_user(F.BOB)
        d2 = self.tasks.get("SP-B")["task"]
        self.assertIsNone(d2["children_progress"])
        self.assertIsNotNone(self.fk.row("PM Task Seen", "SP-B::" + F.BOB))
        inbox = self.fk.load("ecentric_workspace.pm.api.pm_inbox")
        inbox.request_deadline("SP-B", "2026-11-01", "can them")
        p = self.tasks.get("SP-B")["task"]["pending_deadline_request"]
        self.assertEqual((p["new_end"], p["reason"], p["requested_by"]),
                         ("2026-11-01", "can them", F.BOB))

    def test_giver_is_requester_when_task_came_through_a_request(self):
        F.task(self.fk, "T", owner=F.LEADER, assign=[F.ALICE])
        self.fk.add("PM Assignment Request", name="AR", task="T", recipient=F.ALICE,
                    requested_by=F.GIVER, status="Accepted", kind="Assignment")
        self.as_user(F.ALICE)
        self.assertEqual(self.tasks.get("T")["task"]["giver"]["user"], F.GIVER)

    def test_get_denied_for_outsider(self):
        self.fk.add("Project", name="P9", project_name="Kin")
        F.task(self.fk, "T", owner=F.GIVER, assign=[F.ALICE], project="P9")
        self.as_user(F.OUTSIDER)
        with self.assertRaises(F.PermissionError):
            self.tasks.get("T")


# ------------------------------------------------------------------ personal-log exclusion
class TestPersonalLog(Base):
    def setUp(self):
        super(TestPersonalLog, self).setUp()
        self.fk.add("Project", name="WL", project_name="ERP - Nhat ky", ec_personal_log=1,
                    ec_manager=F.LEADER)
        self.fk.add("Project", name="P1", project_name="Du an", ec_personal_log=0,
                    ec_manager=F.LEADER)
        F.task(self.fk, "W1", owner=F.LEADER, assign=[F.LEADER], project="WL")
        F.task(self.fk, "A1", owner=F.LEADER, assign=[F.LEADER], project="P1")
        F.task(self.fk, "N1", owner=F.LEADER, assign=[F.LEADER])  # no project -> never dropped
        self.as_user(F.LEADER)

    def test_tasks_list(self):
        names = sorted(r["name"] for r in self.tasks.list()["rows"])
        self.assertEqual(names, ["A1", "N1"])
        self.assertEqual(sorted(r["name"] for r in self.tasks.list(include_personal=1)["rows"]),
                         ["A1", "N1", "W1"])
        self.assertEqual([r["name"] for r in self.tasks.list(project="WL")["rows"]], ["W1"])
        self.assertEqual(len(self.tasks.list(page_length=1)["rows"]), 1)

    def test_projects_list(self):
        projects = self.fk.load("ecentric_workspace.pm.api.projects")
        rows = projects.list()["rows"]
        self.assertEqual([r["name"] for r in rows], ["P1"])
        self.assertEqual(rows[0]["ec_personal_log"], 0)
        rows = projects.list(include_personal="1")["rows"]
        self.assertEqual({r["name"]: r["ec_personal_log"] for r in rows}, {"P1": 0, "WL": 1})

    def test_dashboard_counts_and_badges(self):
        dash = self.fk.load("ecentric_workspace.pm.api.dashboard")
        self.assertEqual(dash.summary()["my_tasks"], 2)
        self.assertEqual(dash.summary(include_personal=1)["my_tasks"], 3)
        self.assertEqual(sorted(t["name"] for t in dash.my_tasklist()["nodue"]), ["A1", "N1"])
        b = dash.rail_badges()
        self.assertEqual(b["mywork"], 2)
        self.assertIn("received", b)
        cc = dash.control_center()
        self.assertEqual(cc["team"]["active"], 2)


class TestDashboardQuotedLike(Base):
    def test_substring_email_no_longer_matches(self):
        F.task(self.fk, "MINE", owner=F.GIVER, assign=["an@ec.vn"])
        F.task(self.fk, "OTHER", owner=F.GIVER, assign=["tran@ec.vn"])
        self.fk.roles["an@ec.vn"] = ["PM Member"]
        dash = self.fk.load("ecentric_workspace.pm.api.dashboard")
        self.as_user("an@ec.vn")
        self.assertEqual(dash.rail_badges()["mywork"], 1)
        self.assertEqual([t["name"] for t in dash.my_tasklist()["nodue"]], ["MINE"])

    def test_rail_badges_received_and_silent_for_non_pm(self):
        F.task(self.fk, "NEW", owner=F.GIVER, assign=[F.ALICE])
        dash = self.fk.load("ecentric_workspace.pm.api.dashboard")
        self.as_user(F.ALICE)
        self.assertEqual(dash.rail_badges()["received"], 1)
        self.as_user("nopm@ec.vn")
        self.assertEqual(dash.rail_badges(), {"mywork": 0, "assignments": 0, "received": 0})


# ------------------------------------------------------------------ static checks
def _module_literals(path):
    with io.open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    return {t.targets[0].id: t.value for t in tree.body
            if isinstance(t, ast.Assign) and isinstance(t.targets[0], ast.Name)}


class TestEventsRegistered(unittest.TestCase):
    NEW = ("task_deadline_requested", "task_deadline_answered", "task_nudge",
           "task_ready_for_review")

    def test_new_events_in_map_with_task_assigned_defaults(self):
        vals = _module_literals(os.path.join(APP, "notification_center", "events.py"))
        types_ = ast.literal_eval(vals["EVENT_TYPES"])
        sev = ast.literal_eval(vals["_DEFAULT_SEVERITY"])
        matrix = ast.literal_eval(vals["ROUTING_MATRIX"])
        for ev in self.NEW:
            self.assertIn(ev, types_)
            self.assertEqual(sev[ev], sev["task_assigned"])
            self.assertEqual(matrix[ev], matrix["task_assigned"])
        self.assertIn("feedback_update", types_)  # existing entries untouched

    def test_task_flow_uses_the_registered_names(self):
        vals = _module_literals(os.path.join(APP, "pm", "task_flow.py"))
        used = {ast.literal_eval(vals[k]) for k in vals if k.startswith("EV_")}
        self.assertEqual(used, set(self.NEW))


class TestRepoArtifacts(unittest.TestCase):
    def test_patches_registered_in_order_and_files_exist(self):
        with io.open(os.path.join(APP, "patches.txt"), encoding="utf-8") as fh:
            lines = [l.strip() for l in fh.read().split("\n")]
        want = ["ecentric_workspace.pm.patches.p024_pm_redesign_fields",
                "ecentric_workspace.pm.patches.p025_pm_personal_log_projects",
                "ecentric_workspace.pm.patches.p026_pm_split_parent_backfill",
                "ecentric_workspace.pm.patches.p027_pm_task_seen_baseline"]
        idx = [lines.index(w) for w in want]
        self.assertEqual(idx, sorted(idx))
        self.assertGreater(idx[0], lines.index("[post_model_sync]"))
        for w in want:
            self.assertTrue(os.path.exists(os.path.join(F.SRC, *w.split(".")) + ".py"), w)

    def test_pm_task_seen_doctype(self):
        base = os.path.join(APP, "ecentric_workspace", "doctype", "pm_task_seen")
        with io.open(os.path.join(base, "pm_task_seen.json"), encoding="utf-8") as fh:
            j = json.load(fh)
        self.assertEqual(j["name"], "PM Task Seen")
        self.assertEqual(j["module"], "Ecentric Workspace")
        f = {x["fieldname"]: x for x in j["fields"]}
        self.assertEqual((f["task"]["options"], f["user"]["options"]), ("Task", "User"))
        self.assertEqual(f["first_seen"]["fieldtype"], "Datetime")
        self.assertTrue(os.path.exists(os.path.join(base, "pm_task_seen.py")))
        self.assertTrue(os.path.exists(os.path.join(base, "__init__.py")))


# ------------------------------------------------------------------ patches
class TestPatches(Base):
    def test_p024_adds_fields_once(self):
        p = self.fk.load("ecentric_workspace.pm.patches.p024_pm_redesign_fields")
        self.fk.doctypes.add("Custom Field")
        p.execute()
        made = sorted((r["dt"], r["fieldname"]) for r in self.fk.db.t("Custom Field").values())
        self.assertEqual(made, [("PM Assignment Request", "kind"), ("Project", "ec_personal_log"),
                                ("Task", "ec_auto_close"), ("Task", "ec_review_required"),
                                ("Task", "ec_split_parent")])
        self.assertTrue(any("kind = 'Assignment'" in q for q in self.fk.db.sqls))
        self.fk.meta_fields = {"Project": {"ec_personal_log"},
                               "Task": {"ec_auto_close", "ec_review_required", "ec_split_parent"},
                               "PM Assignment Request": {"kind"}}
        p.execute()  # idempotent
        self.assertEqual(len(self.fk.db.t("Custom Field")), 5)

    def test_p025_flags_only_erp_prefix(self):
        self.fk.meta_fields = {"Project": {"ec_personal_log"}}
        self.fk.add("Project", name="A", project_name="ERP - Phan quyen", ec_personal_log=0)
        self.fk.add("Project", name="B", project_name="ERPNext migration", ec_personal_log=0)
        p = self.fk.load("ecentric_workspace.pm.patches.p025_pm_personal_log_projects")
        p.execute()
        self.assertEqual((self.fk.row("Project", "A")["ec_personal_log"],
                          self.fk.row("Project", "B")["ec_personal_log"]), (1, 0))

    def test_p026_and_p027(self):
        self.fk.meta_fields = {"Task": {"ec_split_parent"}}
        F.task(self.fk, "SP", is_group=1, subject="Bao cao", split=0)
        F.task(self.fk, "SP-A", parent_task="SP", subject="Bao cao — Alice", assign=[F.ALICE])
        F.task(self.fk, "G", is_group=1, subject="Nhom", split=0)
        F.task(self.fk, "G-1", parent_task="G", subject="Viec le", assign=[F.BOB], state="Done")
        self.fk.load("ecentric_workspace.pm.patches.p026_pm_split_parent_backfill").execute()
        self.assertEqual((self.fk.row("Task", "SP")["ec_split_parent"],
                          self.fk.row("Task", "G")["ec_split_parent"]), (1, 0))
        p27 = self.fk.load("ecentric_workspace.pm.patches.p027_pm_task_seen_baseline")
        p27.execute()
        p27.execute()
        self.assertEqual(sorted(self.fk.db.t("PM Task Seen")), ["SP-A::" + F.ALICE])


if __name__ == "__main__":
    unittest.main()

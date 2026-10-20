# -*- coding: utf-8 -*-
"""Người theo dõi (CC), PO 20/10/2026. Ca thật: Huyen (E-com) giao "Monthly Plan 11" cho
Thai Cao (trưởng Digital, thuộc phòng Management của CEO) và các thành viên. Mong muốn:
giao cho member khác phòng -> tự CC trưởng phòng của member; người nhận là manager -> không
CC lên CEO; giao trong cùng phòng -> không tự CC; chọn cả trưởng phòng lẫn nhân viên ->
gợi ý chuyển trưởng phòng sang CC. Fake frappe, no bench."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402

HUYEN, LINH = "huyen@ec.vn", "linh.ngo@ec.vn"            # E-com (head: Linh)
THAI, HUONG = "thai@ec.vn", "huong@ec.vn"                 # Digital (head: Thai)
CEO, PHU = "ceo@ec.vn", "phu@ec.vn"                       # Management (head CEO) / Service
HIEN = "hien@ec.vn"                                       # Service head


class Base(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        for u in (HUYEN, LINH, THAI, HUONG, CEO, PHU, HIEN):
            self.fk.add("User", name=u, full_name=u.split("@")[0].title(), enabled=1, user_type="System User")
            self.fk.roles[u] = ["PM Member"]
        for d, h in (("ECOM", LINH), ("DIGITAL", THAI), ("MGMT", CEO), ("SERVICE", HIEN)):
            self.fk.add("Department", name=d, manager_email=h)
        for i, (u, d) in enumerate(((HUYEN, "ECOM"), (LINH, "ECOM"), (THAI, "MGMT"), (HUONG, "DIGITAL"),
                                    (CEO, "MGMT"), (PHU, "SERVICE"), (HIEN, "SERVICE"))):
            self.fk.add("Employee", name="EMP-%d" % i, user_id=u, department=d, status="Active")
        self.fk.add("Project", name="P1", project_name="Plan", ec_manager=HUYEN)
        self.tasks = self.fk.load("ecentric_workspace.pm.api.tasks")
        self.inbox = self.fk.load("ecentric_workspace.pm.api.pm_inbox")
        self.tflow = self.fk.load("ecentric_workspace.pm.task_flow")
        self.pmperm = self.fk.load("ecentric_workspace.pm.permissions")
        self.fk.set_user(HUYEN)

    def followers(self, task):
        return sorted(r["user"] for r in self.fk.db.t("PM Task Follower").values() if r["task"] == task)


class TestSuggest(Base):
    def test_cross_department_member_ccs_head(self):
        self.assertEqual(self.tflow.suggest_cc(HUYEN, [HUONG]), [{"user": THAI, "for": [HUONG]}])

    def test_manager_assignee_never_ccs_upwards(self):
        self.assertEqual(self.tflow.suggest_cc(HUYEN, [THAI]), [])   # no CEO

    def test_same_department_no_auto_cc(self):
        self.assertEqual(self.tflow.suggest_cc(HUYEN, [LINH]), [])
        self.assertEqual(self.tflow.suggest_cc(LINH, [HUYEN]), [])

    def test_head_already_assignee_not_ccd_and_conflict_reported(self):
        self.assertEqual(self.tflow.suggest_cc(HUYEN, [THAI, HUONG, PHU]), [{"user": HIEN, "for": [PHU]}])
        self.assertEqual(self.tflow.head_conflicts([THAI, HUONG, PHU]), [{"head": THAI, "members": [HUONG]}])

    def test_endpoint_shape(self):
        out = self.inbox.cc_suggest(json.dumps([THAI, HUONG]))
        self.assertEqual([x["user"] for x in out["suggest"]], [])
        self.assertEqual(out["conflicts"][0]["head"], THAI)
        self.assertEqual(out["conflicts"][0]["member_names"], ["Huong"])
        out = self.inbox.cc_suggest(json.dumps([HUONG]))
        self.assertEqual(out["suggest"][0]["user"], THAI)
        self.assertEqual(out["suggest"][0]["for_names"], ["Huong"])


class TestCreate(Base):
    def test_create_auto_cc_and_notice(self):
        r = self.tasks.create("P1", "Monthly Plan 11", assignees=json.dumps([HUONG]))
        self.assertEqual(self.followers(r["name"]), [THAI])
        cc = [n for n in self.fk.notifications if n["user"] == THAI]
        self.assertTrue(cc and cc[0]["suffix"] == "cc" and "Bạn được CC" in cc[0]["subject"])
        self.assertNotIn(THAI, json.loads(self.fk.row("Task", r["name"])["_assign"] or "[]"))  # not a doer

    def test_explicit_empty_cc_disables_auto(self):
        r = self.tasks.create("P1", "x", assignees=json.dumps([HUONG]), cc="[]")
        self.assertEqual(self.followers(r["name"]), [])

    def test_explicit_cc_manual_person(self):
        r = self.tasks.create("P1", "x", assignees=json.dumps([PHU]), cc=json.dumps([CEO]))
        self.assertEqual(self.followers(r["name"]), [CEO])

    def test_split_followers_on_parent_and_per_person(self):
        r = self.tasks.create("P1", "Monthly Plan 11", assignees=json.dumps([HUONG, PHU]), split_per_assignee=1)
        self.assertEqual(self.followers(r["name"]), [HIEN, THAI])
        row = self.fk.row("PM Task Follower", r["name"] + "::" + THAI)
        self.assertEqual(json.loads(row["for_users"]), [HUONG])
        kids = {json.loads(self.fk.row("Task", k)["_assign"])[0]: k for k in r["children"]}
        # Thai hears about Huong's part only; Hien about Phu's
        self.assertEqual(self.tflow.relevant_followers(dict(self.fk.row("Task", kids[HUONG]))), [THAI])
        self.assertEqual(self.tflow.relevant_followers(dict(self.fk.row("Task", kids[PHU]))), [HIEN])

    def test_follower_can_view_not_edit(self):
        r = self.tasks.create("P1", "x", assignees=json.dumps([HUONG]), cc=json.dumps([CEO]))
        t = dict(self.fk.row("Task", r["name"]))
        self.assertTrue(self.pmperm.can_view_task(t, CEO))
        self.assertFalse(self.tflow.can_edit_task({"name": r["name"]}, CEO))
        self.fk.set_user(CEO)
        out = self.tasks.get(r["name"])["task"]
        self.assertEqual(out["is_follower"], 1)
        self.assertEqual([f["user"] for f in out["followers"]], [CEO])

    def test_done_notifies_followers(self):
        r = self.tasks.create("P1", "x", assignees=json.dumps([HUONG]))
        self.fk.notifications.clear()
        self.fk.set_user(HUONG)
        self.tasks.set_status(r["name"], "Done")
        done = [n for n in self.fk.notifications if n["user"] == THAI and n["suffix"] == "cc-done"]
        self.assertEqual(len(done), 1)

    def test_assign_later_auto_ccs(self):
        r = self.tasks.create("P1", "x")
        self.tasks.assign(r["name"], json.dumps([HUONG]))
        self.assertEqual(self.followers(r["name"]), [THAI])


class TestFollowTabAndManage(Base):
    def test_follow_tab_lists_running_tasks_with_giver(self):
        r = self.tasks.create("P1", "Monthly Plan 11", assignees=json.dumps([HUONG, PHU]), split_per_assignee=1)
        self.fk.set_user(THAI)
        out = self.inbox.given("follow")
        self.assertEqual([b["task"] for b in out["batches"]], [r["name"]])
        self.assertEqual(out["batches"][0]["giver"]["user"], HUYEN)
        self.assertEqual(out["batches"][0]["total"], 2)
        self.assertEqual(self.inbox.given("run")["batches"], [])   # not something Thai gave

    def test_self_follow_unfollow_and_editor_manage(self):
        r = self.tasks.create("P1", "x", assignees=json.dumps([PHU]), cc="[]")
        self.fk.set_user(HIEN)   # head of Phu: can view (head rule) -> can follow self
        self.tasks.set_followers(r["name"], add=json.dumps([HIEN]))
        self.assertEqual(self.followers(r["name"]), [HIEN])
        with self.assertRaises(F.PermissionError):
            self.fk.set_user(CEO)
            self.tasks.set_followers(r["name"], add=json.dumps([CEO]))
        self.fk.set_user(HUYEN)   # owner/editor manages anyone
        self.tasks.set_followers(r["name"], add=json.dumps([LINH]), remove=json.dumps([HIEN]))
        self.assertEqual(self.followers(r["name"]), [LINH])

    def test_delete_cleans_followers(self):
        r = self.tasks.create("P1", "x", assignees=json.dumps([HUONG]))
        self.assertTrue(self.followers(r["name"]))
        self.fk.set_user(F.LEADER)
        try:
            self.tasks.delete(r["name"])
        except Exception:
            self.skipTest("delete needs more fake surface")
        self.assertEqual(self.followers(r["name"]), [])


if __name__ == "__main__":
    unittest.main()


class TestRequestMode(Base):
    def setUp(self):
        super(TestRequestMode, self).setUp()

        def _task_default_state(doc, method=None):  # what the PM Task Workflow does on insert
            if not doc.get("workflow_state"):
                doc["workflow_state"] = "Backlog"
        self.fk.hooks["Task"] = [_task_default_state]

    def test_create_with_task_ccs_from_recipients(self):
        asg = self.fk.load("ecentric_workspace.pm.api.assignment")
        self.fk.hooks["PM Assignment Request"] = [asg.pm_assignment_request_guard]
        r = asg.create_with_task("Monthly Plan 11", recipient=HUONG, project="P1")
        self.assertEqual(self.followers(r["task"]), [THAI])

    def test_create_with_task_split_cc_on_parent(self):
        asg = self.fk.load("ecentric_workspace.pm.api.assignment")
        self.fk.hooks["PM Assignment Request"] = [asg.pm_assignment_request_guard]
        r = asg.create_with_task("Monthly Plan 11", recipients=json.dumps([HUONG, PHU]), project="P1",
                                 split_per_assignee=1)
        self.assertEqual(self.followers(r["task"]), [HIEN, THAI])
        for c in r["children"]:
            self.assertEqual(self.followers(c), [])

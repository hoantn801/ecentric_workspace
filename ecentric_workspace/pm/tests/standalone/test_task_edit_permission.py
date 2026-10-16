# -*- coding: utf-8 -*-
"""PO 16/10/2026 ("siết lại"): xem được != sửa được. task_flow.can_edit_task + the write
endpoints that enforce it (tasks.set_status/mark_done/update/assign/create sub-task,
checklist.add_item). Viewers (e.g. same department via project visibility) are read-only."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402

VIEWER = "viewer@ec.vn"
PM_BOSS = "pmboss@ec.vn"


class TestTaskEditPermission(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        for u in (VIEWER, PM_BOSS):
            self.fk.add("User", name=u, full_name=u, enabled=1, user_type="System User")
            self.fk.roles[u] = ["PM Member"]
        self.fk.add("Project", name="P1", project_name="Du an 1", ec_manager=PM_BOSS)
        self.tasks = self.fk.load("ecentric_workspace.pm.api.tasks")
        self.tflow = self.fk.load("ecentric_workspace.pm.task_flow")
        self.pmperm = self.fk.load("ecentric_workspace.pm.permissions")
        F.task(self.fk, "T", owner=F.GIVER, assign=[F.ALICE], project="P1", state="To Do")
        F.task(self.fk, "C", owner=F.GIVER, assign=[], project="P1", parent_task="T")
        # the viewer can SEE every task of P1 (department visibility), nothing more
        real = self.pmperm.can_view_task
        self.pmperm.can_view_task = lambda t, u=None: (u or self.fk.session.user) == VIEWER or real(t, u)

    def as_user(self, u):
        self.fk.set_user(u)

    def test_rule(self):
        ce = self.tflow.can_edit_task
        self.assertTrue(ce({"name": "T"}, F.GIVER))     # owner / giver
        self.assertTrue(ce({"name": "T"}, F.ALICE))     # assignee
        self.assertTrue(ce({"name": "T"}, PM_BOSS))     # project manager
        self.assertTrue(ce({"name": "T"}, F.LEADER))    # PM leader (System Manager)
        self.assertFalse(ce({"name": "T"}, VIEWER))     # sees it, not responsible
        self.assertFalse(ce({"name": "T"}, F.BOB))
        self.assertTrue(ce({"name": "C"}, F.ALICE))     # parent's assignee manages sub-tasks

    def test_viewer_cannot_change_status_or_done(self):
        self.as_user(VIEWER)
        with self.assertRaises(F.PermissionError):
            self.tasks.set_status("T", "In Progress")
        with self.assertRaises(F.PermissionError):
            self.tasks.mark_done("T")
        self.assertEqual(self.fk.row("Task", "T")["workflow_state"], "To Do")

    def test_viewer_cannot_assign_or_add_subtask(self):
        self.as_user(VIEWER)
        with self.assertRaises(F.PermissionError):
            self.tasks.assign("T", '["%s"]' % F.BOB)
        with self.assertRaises(F.PermissionError):
            self.tasks.create(project="P1", subject="x", parent_task="T")

    def test_assignee_and_manager_still_can(self):
        self.as_user(F.ALICE)
        self.tasks.set_status("T", "In Progress")
        self.assertEqual(self.fk.row("Task", "T")["workflow_state"], "In Progress")
        self.as_user(PM_BOSS)
        self.tasks.set_status("T", "To Do")
        self.assertEqual(self.fk.row("Task", "T")["workflow_state"], "To Do")

    def _head_setup(self):
        HEAD = "head@ec.vn"
        self.fk.add("User", name=HEAD, full_name="Truong Phong", enabled=1, user_type="System User")
        self.fk.roles[HEAD] = ["PM Member"]
        self.fk.add("Department", name="D-OPS", manager_email=HEAD)
        self.fk.add("Employee", name="EMP-A", user_id=F.ALICE, department="D-OPS", status="Active")
        F.task(self.fk, "T2", owner=F.GIVER, assign=[F.ALICE], state="To Do")
        return HEAD

    def test_department_head_can_view_edit_and_comment(self):
        HEAD = self._head_setup()
        self.assertTrue(self.pmperm.can_view_task({"name": "T2", "owner": F.GIVER, "project": None}, HEAD))
        self.assertFalse(self.pmperm.can_view_task({"name": "T2", "owner": F.GIVER, "project": None}, F.BOB))
        self.assertTrue(self.tflow.can_edit_task({"name": "T2"}, HEAD))
        self.assertFalse(self.tflow.can_edit_task({"name": "T2"}, F.BOB))
        self.as_user(HEAD)
        self.tasks.set_status("T2", "In Progress")
        self.assertEqual(self.fk.row("Task", "T2")["workflow_state"], "In Progress")
        self.fk.doctypes.add("Comment")
        self.fk.module.utils.sanitize_html = lambda s: s
        cm = self.fk.load("ecentric_workspace.pm.api.comments")
        cm.add("Task", "T2", "Truong phong nhac")   # chat duoc
        self.assertTrue(any(c.get("reference_name") == "T2" for c in self.fk.db.t("Comment").values()))

    def test_head_of_other_department_cannot(self):
        HEAD = self._head_setup()
        self.fk.add("Employee", name="EMP-B", user_id=F.BOB, department="D-OTHER", status="Active")
        F.task(self.fk, "TB", owner=F.GIVER, assign=[F.BOB], state="To Do")
        self.assertFalse(self.tflow.can_edit_task({"name": "TB"}, HEAD))

    def test_get_exposes_can_edit(self):
        self.as_user(VIEWER)
        self.assertEqual(self.tasks.get("T")["task"]["can_edit"], 0)
        self.as_user(F.ALICE)
        self.assertEqual(self.tasks.get("T")["task"]["can_edit"], 1)


if __name__ == "__main__":
    unittest.main()

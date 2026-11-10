# Copyright (c) 2026, eCentric and contributors
"""pm_gateway chay THAT tren service PM (pm.api.tasks.create / update / set_status, pm.task_flow.write_state)
voi frappe gia cua chinh bo test PM (pm/tests/standalone/_pm_fake.py) - kiem tham so gateway truyen
dung hop dong cua PM, va listener `ec_pm_task_state_listeners` duoc goi khi /pm doi trang thai.

    python -m unittest ecentric_workspace.data_hub.tests.test_pm_gateway
"""
import contextlib
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PM_FAKE = os.path.abspath(os.path.join(HERE, "..", "..", "pm", "tests", "standalone"))


class TestGatewayOnRealPm(unittest.TestCase):
    def setUp(self):
        self.saved = dict(sys.modules)
        sys.path.insert(0, PM_FAKE)
        import _pm_fake as F
        self.F = F
        self.fk = F.install()
        F.seed_users(self.fk)
        self.fk.add("Project", name="PROJ-0042", project_name="Trung tâm Dữ liệu", ec_manager=F.LEADER,
                    expected_start_date=None, expected_end_date=None)
        fk = self.fk
        fk.module.get_hooks = lambda key: list(fk.hooks.get("__" + key, []))
        fk.module.get_attr = lambda path: fk.hooks["__attr__" + path]
        from ecentric_workspace.data_hub import repository as R

        @contextlib.contextmanager
        def as_system():
            prev = fk.session.user
            fk.set_user("Administrator")
            try:
                yield
            finally:
                fk.set_user(prev)
        R.as_system = as_system
        self.G = fk.load("ecentric_workspace.data_hub.pm_gateway")
        self.tasks = fk.load("ecentric_workspace.pm.api.tasks")

    def tearDown(self):
        sys.path.remove(PM_FAKE)
        for k in list(sys.modules):
            if k not in self.saved:
                sys.modules.pop(k)
        sys.modules.update(self.saved)

    def test_create_update_assign_state(self):
        import datetime as dt
        F, fk = self.F, self.fk
        fk.set_user(F.ALICE)          # nguoi bam Nhan tren Trung tam Du lieu
        name = self.G.create_task("PROJ-0042", "[DR-2026-0001] PnL", "<p>mo ta</p>", F.BOB,
                                  dt.date(2026, 10, 16), dt.date(2026, 10, 23), "High")
        row = fk.row("Task", name)
        self.assertEqual((row["project"], row["subject"], row["priority"], str(row["exp_start_date"])[:10],
                          str(row["exp_end_date"])[:10]), ("PROJ-0042", "[DR-2026-0001] PnL", "High", "2026-10-16", "2026-10-23"))
        self.assertEqual(json.loads(row["_assign"]), [F.BOB])
        self.assertEqual(fk.session.user, F.ALICE, "as_system tra lai phien")
        self.G.update_task(name, exp_start_date=dt.date(2026, 10, 16), exp_end_date=dt.date(2026, 10, 28))
        self.assertEqual(str(fk.row("Task", name)["exp_end_date"])[:10], "2026-10-28")
        self.G.set_assignee(name, F.GIVER, F.BOB)
        self.assertEqual(json.loads(fk.row("Task", name)["_assign"]), [F.GIVER], "go nguoi cu, giao nguoi moi")
        self.G.set_state(name, "In Progress")
        self.G.set_state(name, "Done")
        self.assertEqual(fk.row("Task", name)["workflow_state"], "Done")
        self.G.set_state(name, "Done")        # da Done -> khong goi lai
        self.G.set_state(name, "In Progress")
        self.assertEqual(fk.row("Task", name)["workflow_state"], "In Progress")

    def test_form_dict_of_hub_request_does_not_leak(self):
        """Request cua Trung tam Du lieu co assignee=/priority= trong form_dict: tasks.update KHONG duoc
        hieu la "go nguoi nhan" (gateway lam rong form_dict truoc khi goi PM)."""
        import datetime as dt
        F, fk = self.F, self.fk
        name = self.G.create_task("PROJ-0042", "S", "", F.BOB, dt.date(2026, 10, 16), dt.date(2026, 10, 20), "Medium")
        fk.module.local.form_dict = {"code": "DR-1", "assignee": "", "priority": "Cao", "due_date": "2026-10-30"}
        self.G.update_task(name, exp_end_date=dt.date(2026, 10, 30))
        self.assertEqual(json.loads(fk.row("Task", name)["_assign"]), [F.BOB])

    def test_write_state_calls_listener(self):
        F, fk = self.F, self.fk
        seen = []
        fk.hooks["__ec_pm_task_state_listeners"] = ["x.listener"]
        fk.hooks["__attr__x.listener"] = lambda name, cur, target, user: seen.append((name, cur, target, user))
        F.task(fk, "T1", assign=[F.ALICE])
        fk.set_user(F.ALICE)
        self.tasks.mark_done("T1")
        self.assertEqual(seen, [("T1", "To Do", "Done", F.ALICE)])
        fk.hooks["__attr__x.listener"] = lambda *a: 1 / 0
        F.task(fk, "T2", assign=[F.ALICE])
        self.assertEqual(self.tasks.mark_done("T2"), {"state": "Done"}, "listener loi khong lam hong /pm")

    def test_hub_listener_end_to_end(self):
        """/pm bam Xong -> listener that cua Trung tam Du lieu -> ticket Cho nghiem thu (repo gia)."""
        F, fk = self.F, self.fk
        from ecentric_workspace.data_hub.tests import fake as DF
        from ecentric_workspace.data_hub import constants as C, ops_service as O, pm_sync as P, service as S
        import ecentric_workspace.data_hub as pkg
        repo = DF.FakeRepo()
        repo.flags_ = fk.module.flags
        fk.roles[DF.LINH] = ["PM Member"]
        fk.add("User", name=DF.LINH, full_name="Linh", enabled=1, user_type="System User")
        code = S.create(DF.THU, DF.req(), repo=repo)["code"]
        O.accept(DF.LINH, code, DF.LINH, repo=repo, pm=self.G)
        task = repo.get(code)["pm_task"]
        self.assertEqual(fk.row("Task", task)["workflow_state"], "In Progress")
        pkg.repository = repo
        sys.modules["ecentric_workspace.data_hub.repository"] = repo
        fk.hooks["__ec_pm_task_state_listeners"] = ["ecentric_workspace.data_hub.pm_sync.on_task_state"]
        fk.hooks["__attr__ecentric_workspace.data_hub.pm_sync.on_task_state"] = P.on_task_state
        fk.set_user(DF.LINH)
        self.tasks.mark_done(task)
        self.assertEqual(repo.get(code)["status"], C.ST_REVIEW)
        done = [lg for lg in repo.logs_ if lg["event"] == C.EV_DONE][-1]
        self.assertEqual((done["source"], done["actor"]), (C.SRC_PM, DF.LINH))
        # Trung tam bam Hoan tat -> /pm Done qua gateway; listener thay co -> khong ap nguoc
        S.respond(DF.THU, code, C.ACC_FAIL, "thiếu cột", repo=repo, pm=self.G)
        self.assertEqual(fk.row("Task", task)["workflow_state"], "In Progress")
        self.assertEqual(repo.get(code)["status"], C.ST_DOING)
        n = len(repo.logs_)
        O.mark_done(DF.LINH, code, repo=repo, pm=self.G)
        self.assertEqual(fk.row("Task", task)["workflow_state"], "Done")
        self.assertEqual([lg["event"] for lg in repo.logs_[n:]], [C.EV_DONE], "khong ghi doi (vong lap bi chan)")


if __name__ == "__main__":
    unittest.main()

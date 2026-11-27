# -*- coding: utf-8 -*-
"""Hotfix 23 (27/11/2026) backend: /pm thiết kế lại.

  colors      pm/colors.py: phòng ban -> khoá màu, băm tên cho phòng ban mới, ec_color ghi đè.
  projects    list scope/q/counts/total + row health/color/can_manage/can_delete (tương thích cũ),
              detail health/color/can_manage, set_status, set_color, delete mở cho quản lý dự án.
  queue       rows có project_color.
  coordinate  phân trang 2 khối todo / people (mặc định 7) + todo_total / people_total.
  timesheet   report: top_tasks có subject, by_project, people phân trang; export_xlsx cùng quyền.
Fake 'today' = 2026-10-16 (_pm_fake)."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402

DEPT = "E-commerce Operation - EC"
MGR = "mgr@ec.vn"          # PM Member, manages P_RUN, same department as ALICE


class Base(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.fk.add("User", name=MGR, full_name="Ma Nager", enabled=1, user_type="System User")
        self.fk.roles[MGR] = ["PM Member"]
        self.fk.doctypes.add("Employee")
        self.fk.add("Employee", name="EMP-A", user_id=F.ALICE, status="Active", department=DEPT)
        self.fk.add("Employee", name="EMP-M", user_id=MGR, status="Active", department=DEPT)
        self.fk.meta_fields["Project"] = {"ec_color", "ec_department", "ec_manager"}
        self.pr = self.fk.load("ecentric_workspace.pm.api.projects")
        self.col = self.fk.load("ecentric_workspace.pm.colors")

    def me(self, u):
        self.fk.set_user(u)

    def proj(self, name, status="Open", dept=DEPT, mgr=MGR, owner=F.GIVER, **kw):
        return self.fk.add("Project", name=name, project_name=kw.pop("project_name", "Du an " + name),
                           status=status, ec_department=dept, ec_manager=mgr, owner=owner, **kw)


# ------------------------------------------------------------------ colors
class TestColors(Base):
    def test_dept_map_ignores_company_suffix(self):
        self.assertEqual(self.col.color_for({"ec_department": "E-commerce Operation - EC"}), "navy")
        self.assertEqual(self.col.color_for({"ec_department": "Service"}), "violet")
        self.assertEqual(self.col.color_for({"ec_department": "production - EC"}), "rose")
        self.assertEqual(self.col.color_for({"ec_department": "Operation & Data & System - EC"}), "teal")

    def test_unmapped_dept_hash_is_stable_and_valid(self):
        a = self.col.color_for({"ec_department": "Finance - EC"})
        self.assertIn(a, self.col.PALETTE_KEYS)
        self.assertEqual(a, self.col.color_for({"ec_department": "Finance - XY"}))
        self.assertEqual(a, self.col.hashed_key("finance"))

    def test_override_and_fallbacks(self):
        self.assertEqual(self.col.color_for({"ec_color": "amber", "ec_department": "Service"}), "amber")
        self.assertEqual(self.col.color_for({"ec_color": "pink", "ec_department": "Service"}), "violet")
        self.assertEqual(self.col.color_for({"ec_department": None}), self.col.NO_DEPT_COLOR)
        self.assertEqual(self.col.PALETTE_KEYS,
                         ("navy", "violet", "sky", "teal", "green", "amber", "rose", "slate"))

    def test_fixture_options_match_palette(self):
        import json
        path = os.path.join(F.SRC, "ecentric_workspace", "fixtures", "custom_field.json")
        with open(path, encoding="utf-8") as fh:
            cf = [x for x in json.load(fh) if x["name"] == "Project-ec_color"]
        self.assertEqual(len(cf), 1)
        self.assertEqual((cf[0]["dt"], cf[0]["fieldname"], cf[0]["fieldtype"]), ("Project", "ec_color", "Select"))
        self.assertEqual(cf[0]["options"].split("\n"), [""] + list(self.col.PALETTE_KEYS))


# ------------------------------------------------------------------ projects.list
class TestProjectList(Base):
    def setUp(self):
        super(TestProjectList, self).setUp()
        self.proj("P_RUN", project_name="Andros Q4")
        self.proj("P_DONE", status="Completed", project_name="Andros Q3")
        self.proj("P_CXL", status="Cancelled", project_name="Bot")
        self.proj("P_OTHER", dept="Service - EC", mgr=F.BOB, project_name="Service X")
        self.proj("P_EMPTY", project_name="Trong", ec_color="green")
        # P_RUN: 9 open (4 late, 1 blocked? no) + 1 done
        for i in range(4):
            F.task(self.fk, "L%d" % i, assign=[F.ALICE], project="P_RUN", end="2026-10-0%d" % (i + 1))
        for i in range(5):
            F.task(self.fk, "O%d" % i, assign=[F.ALICE], project="P_RUN", end="2026-10-30")
        F.task(self.fk, "D0", assign=[F.ALICE], project="P_RUN", state="Done", end="2026-10-01")
        F.task(self.fk, "X0", assign=[F.BOB], project="P_OTHER", end="2026-10-30")

    def test_legacy_call_shape_and_rows(self):
        self.me(F.LEADER)
        r = self.pr.list(page_length=500)
        self.assertEqual(set(r), {"rows", "total", "counts"})
        self.assertEqual(r["total"], 5)
        self.assertEqual(len(r["rows"]), 5)
        row = [x for x in r["rows"] if x["name"] == "P_RUN"][0]
        for k in ("task_total", "task_done", "progress", "ec_personal_log", "open", "late", "unassigned",
                  "health", "health_text", "color_key", "can_manage", "can_delete", "ec_manager_name"):
            self.assertIn(k, row)
        self.assertEqual((row["task_total"], row["task_done"], row["progress"], row["open"], row["late"]),
                         (10, 1, 10, 9, 4))
        self.assertEqual(row["color_key"], "navy")
        self.assertEqual(row["ec_manager_name"], "Ma Nager")
        self.assertEqual([x["color_key"] for x in r["rows"] if x["name"] == "P_EMPTY"], ["green"])

    def test_health_formula_and_text(self):
        self.me(F.LEADER)
        rows = {x["name"]: x for x in self.pr.list(page_length=0)["rows"]}
        self.assertEqual(rows["P_RUN"]["health"], "hi")
        self.assertEqual(rows["P_RUN"]["health_text"], "4 việc quá hạn trên 9 việc đang mở")
        self.assertEqual((rows["P_EMPTY"]["health"], rows["P_EMPTY"]["health_text"]), ("", "Chưa có việc"))
        self.assertEqual((rows["P_DONE"]["health"], rows["P_DONE"]["health_text"]), ("", "Dự án đã hoàn thành"))
        self.assertEqual(rows["P_OTHER"]["health"], "ok")
        # same verdict as projects.detail risk_level (single formula)
        d = self.pr.detail("P_RUN")
        self.assertEqual((d["risk_level"], d["health"], d["health_text"]), ("high", "hi", rows["P_RUN"]["health_text"]))

    def test_health_mid_and_blocked(self):
        self.proj("P_MID")
        for i in range(3):
            F.task(self.fk, "M%d" % i, assign=[], project="P_MID")      # no assignee, no due
        self.proj("P_BLK")
        F.task(self.fk, "B0", assign=[F.ALICE], project="P_BLK", state="Blocked", end="2026-10-30")
        self.me(F.LEADER)
        rows = {x["name"]: x for x in self.pr.list(page_length=0)["rows"]}
        self.assertEqual(rows["P_MID"]["health"], "mid")
        self.assertEqual(rows["P_MID"]["health_text"], "3 việc chưa giao, 3 việc chưa có hạn trên 3 việc")
        self.assertEqual(rows["P_MID"]["unassigned"], 3)
        self.assertEqual((rows["P_BLK"]["health"], rows["P_BLK"]["health_text"]), ("hi", "1 việc đang bị chặn"))
        self.assertEqual(self.pr.detail("P_MID")["risk_level"], "medium")

    def test_scopes_counts_q_paging(self):
        self.me(F.LEADER)
        r = self.pr.list(scope="run", page_length=10)
        self.assertEqual(sorted(x["name"] for x in r["rows"]), ["P_EMPTY", "P_OTHER", "P_RUN"])
        self.assertEqual(r["counts"], {"run": 3, "closed": 2, "mine": 0})
        self.assertEqual(sorted(x["name"] for x in self.pr.list(scope="closed")["rows"]), ["P_CXL", "P_DONE"])
        p1 = self.pr.list(scope="run", start=0, page_length=2)
        p2 = self.pr.list(scope="run", start=2, page_length=2)
        self.assertEqual((len(p1["rows"]), p1["total"], len(p2["rows"]), p2["total"]), (2, 3, 1, 3))
        q = self.pr.list(q="Andros")   # MariaDB LIKE is case-insensitive; the fake is not
        self.assertEqual((sorted(x["name"] for x in q["rows"]), q["counts"]["run"], q["counts"]["closed"]),
                         (["P_DONE", "P_RUN"], 1, 1))
        self.me(MGR)
        m = self.pr.list(scope="mine")
        self.assertEqual(sorted(x["name"] for x in m["rows"]), ["P_CXL", "P_DONE", "P_EMPTY", "P_RUN"])
        self.assertEqual(m["counts"]["mine"], 4)

    def test_mine_empty_and_bad_scope(self):
        self.me(F.ALICE)
        r = self.pr.list(scope="mine")
        self.assertEqual((r["rows"], r["total"], r["counts"]["mine"]), ([], 0, 0))
        with self.assertRaises(F.ValidationError):
            self.pr.list(scope="all")

    def test_visibility_kept(self):
        self.me(F.OUTSIDER)
        r = self.pr.list(page_length=200)
        self.assertEqual((r["rows"], r["total"]), ([], 0))
        self.assertEqual(r["counts"], {"run": 0, "closed": 0, "mine": 0})
        self.me(F.ALICE)   # department member sees the department's projects, not Service
        names = sorted(x["name"] for x in self.pr.list(page_length=200)["rows"])
        self.assertEqual(names, ["P_CXL", "P_DONE", "P_EMPTY", "P_RUN"])

    def test_manage_and_delete_flags(self):
        self.me(MGR)
        rows = {x["name"]: x for x in self.pr.list(page_length=0)["rows"]}
        self.assertTrue(rows["P_RUN"]["can_manage"])
        self.assertFalse(rows["P_RUN"]["can_delete"])          # has tasks
        self.assertTrue(rows["P_EMPTY"]["can_delete"])
        self.me(F.ALICE)
        rows = {x["name"]: x for x in self.pr.list(page_length=0)["rows"]}
        self.assertFalse(rows["P_EMPTY"]["can_manage"])
        self.assertFalse(rows["P_EMPTY"]["can_delete"])
        self.me(F.LEADER)
        rows = {x["name"]: x for x in self.pr.list(page_length=0)["rows"]}
        self.assertTrue(rows["P_OTHER"]["can_manage"])

    def test_can_delete_uses_unscoped_count(self):
        # Assignment-only viewer sees 0 of their own tasks? manager sees all -> count authoritative
        self.proj("P_HID", mgr=MGR)
        F.task(self.fk, "H0", owner=F.BOB, assign=[F.BOB], project="P_HID")
        self.me(MGR)
        row = [x for x in self.pr.list(page_length=0)["rows"] if x["name"] == "P_HID"][0]
        self.assertFalse(row["can_delete"])

    def test_no_pm_access(self):
        self.me("nopm@ec.vn")
        with self.assertRaises(F.PermissionError):
            self.pr.list()


# ------------------------------------------------------------------ detail / set_status / set_color / delete
class TestProjectWrites(Base):
    def setUp(self):
        super(TestProjectWrites, self).setUp()
        self.proj("P1")
        self.proj("P0")
        F.task(self.fk, "T1", assign=[F.ALICE], project="P1", end="2026-10-30")

    def test_detail_additions(self):
        self.me(MGR)
        d = self.pr.detail("P1")
        self.assertEqual((d["project"]["color_key"], d["can_manage"], d["can_delete"], d["health"]),
                         ("navy", True, False, "ok"))
        self.assertIn("1 việc đang mở", d["health_text"])
        self.me(F.ALICE)
        self.assertFalse(self.pr.detail("P1")["can_manage"])

    def test_set_status_manager_and_leader(self):
        self.me(MGR)
        self.assertEqual(self.pr.set_status("P1", "Completed"), {"name": "P1", "status": "Completed"})
        self.assertEqual(self.fk.row("Project", "P1")["status"], "Completed")
        self.assertIn(("Project", "P1"), self.fk.saved)             # doc.save() -> Version
        self.assertEqual(self.pr.set_status("P1", "Open")["status"], "Open")
        self.me(F.LEADER)
        self.assertEqual(self.pr.set_status("P1", "Cancelled")["status"], "Cancelled")

    def test_status_pinned_against_erpnext_recompute(self):
        """QC 27/11: ERPNext Project.validate re-derives status from % done unless method = Manual."""
        self.me(MGR)
        self.pr.set_status("P1", "Completed")                       # project still has an open task
        self.assertEqual(self.fk.row("Project", "P1").get("percent_complete_method"), "Manual")
        self.pr.set_status("P1", "Open")
        self.assertEqual(self.fk.row("Project", "P1").get("percent_complete_method"), "Manual")
        doc = types.SimpleNamespace(status="Completed", percent_complete_method="Task Completion")
        doc.get = lambda k, d=None: getattr(doc, k, d)
        self.pr._pin_status(doc)                                    # editing a closed project (colour / form)
        self.assertEqual(doc.percent_complete_method, "Manual")
        doc2 = types.SimpleNamespace(status="Open", percent_complete_method="Task Completion")
        doc2.get = lambda k, d=None: getattr(doc2, k, d)
        self.pr._pin_status(doc2)                                   # open project untouched unless forced
        self.assertEqual(doc2.percent_complete_method, "Task Completion")

    def test_q_escapes_like_wildcards(self):
        self.proj("PX", project_name="a_b")
        self.proj("PY", project_name="axb")
        self.me(F.LEADER)
        names = [r["name"] for r in self.pr.list(page_length=0, q="a_b")["rows"]]
        self.assertNotIn("PY", names)

    def test_set_status_denied_and_invalid(self):
        self.me(F.ALICE)
        with self.assertRaises(F.PermissionError) as cm:
            self.pr.set_status("P1", "Completed")
        self.assertIn("Chỉ quản lý dự án", str(cm.exception))
        self.assertEqual(self.fk.row("Project", "P1")["status"], "Open")
        self.me(MGR)
        with self.assertRaises(F.ValidationError):
            self.pr.set_status("P1", "Closed")
        with self.assertRaises(F.ValidationError):
            self.pr.set_status("NOPE", "Completed")
        self.me("nopm@ec.vn")
        with self.assertRaises(F.PermissionError):
            self.pr.set_status("P1", "Completed")

    def test_set_color(self):
        self.me(MGR)
        self.assertEqual(self.pr.set_color("P1", "amber"), {"name": "P1", "color_key": "amber", "ec_color": "amber"})
        self.assertEqual(self.fk.row("Project", "P1")["ec_color"], "amber")
        self.assertEqual(self.pr.set_color("P1", ""), {"name": "P1", "color_key": "navy", "ec_color": ""})
        with self.assertRaises(F.ValidationError):
            self.pr.set_color("P1", "pink")
        self.me(F.ALICE)
        with self.assertRaises(F.PermissionError):
            self.pr.set_color("P1", "rose")

    def test_set_color_without_field(self):
        self.fk.meta_fields["Project"] = {"ec_department"}
        self.me(MGR)
        with self.assertRaises(F.ValidationError) as cm:
            self.pr.set_color("P1", "rose")
        self.assertIn("ec_color", str(cm.exception))
        # list still works and falls back to the department colour
        self.assertEqual({x["color_key"] for x in self.pr.list(page_length=0)["rows"]}, {"navy"})

    def test_delete_opened_to_manager(self):
        self.me(MGR)
        self.assertEqual(self.pr.delete("P0"), {"deleted": "P0"})
        self.assertIsNone(self.fk.row("Project", "P0"))
        with self.assertRaises(F.ValidationError) as cm:
            self.pr.delete("P1")
        self.assertIn("1 việc", str(cm.exception))
        self.assertIsNotNone(self.fk.row("Project", "P1"))

    def test_delete_denied_for_member(self):
        self.me(F.ALICE)
        with self.assertRaises(F.PermissionError):
            self.pr.delete("P0")
        self.assertIsNotNone(self.fk.row("Project", "P0"))
        self.me(F.LEADER)
        self.assertEqual(self.pr.delete("P0"), {"deleted": "P0"})


# ------------------------------------------------------------------ queue project_color
class TestQueueColor(Base):
    def test_rows_carry_project_color(self):
        self.proj("P1", ec_color="teal")
        self.proj("P2", dept="Service - EC")
        F.task(self.fk, "A", owner=F.GIVER, assign=[F.ALICE], project="P1", end="2026-10-17")
        F.task(self.fk, "B", owner=F.GIVER, assign=[F.ALICE], project="P2", end="2026-10-17")
        F.task(self.fk, "C", owner=F.GIVER, assign=[F.ALICE], end="2026-10-17")
        q = self.fk.load("ecentric_workspace.pm.api.queue")
        self.me(F.ALICE)
        rows = {r["name"]: r for r in q.list()["rows"]}
        self.assertEqual((rows["A"]["project_color"], rows["B"]["project_color"], rows["C"]["project_color"]),
                         ("teal", "violet", ""))


# ------------------------------------------------------------------ coordinate paging
class TestCoordinatePaging(Base):
    def setUp(self):
        super(TestCoordinatePaging, self).setUp()
        self.inbox = self.fk.load("ecentric_workspace.pm.api.pm_inbox")
        self.proj("P1")
        self.users = ["u%02d@ec.vn" % i for i in range(10)]
        for i, u in enumerate(self.users):
            F.task(self.fk, "LATE%02d" % i, assign=[u], project="P1", end="2026-10-%02d" % (i + 1))
        F.task(self.fk, "FREE", assign=[], project="P1", end="2026-10-30")

    def test_default_pages_of_seven(self):
        self.me(F.LEADER)
        r = self.inbox.coordinate()
        self.assertEqual((len(r["todo"]), r["todo_total"]), (7, 11))     # 10 late + 1 unassigned group
        self.assertEqual([x["task"] for x in r["todo"]], ["LATE%02d" % i for i in range(7)])
        self.assertEqual((len(r["people"]), r["people_total"]), (7, 10))
        self.assertIn("full_name", r["people"][0])
        self.assertIn("kpi", r)
        self.assertEqual(r["kpi"]["late"], 10)

    def test_second_page_crosses_into_groups(self):
        self.me(F.LEADER)
        r = self.inbox.coordinate(todo_start=7, todo_len=7, people_start=7, people_len=7)
        self.assertEqual([x.get("task") or x["kind"] for x in r["todo"]],
                         ["LATE07", "LATE08", "LATE09", "unassigned"])
        self.assertEqual(len(r["people"]), 3)
        r = self.inbox.coordinate(todo_start=50)
        self.assertEqual((r["todo"], r["todo_total"]), ([], 11))

    def test_bad_paging_args_fall_back(self):
        self.me(F.LEADER)
        r = self.inbox.coordinate(todo_start="x", todo_len="-3", people_len="abc")
        self.assertEqual((len(r["todo"]), len(r["people"])), (7, 7))

    def test_non_leader_denied(self):
        self.me(MGR)
        with self.assertRaises(F.PermissionError):
            self.inbox.coordinate(todo_start=0, todo_len=7)


# ------------------------------------------------------------------ timesheet
class TestTimesheet(Base):
    def setUp(self):
        super(TestTimesheet, self).setUp()
        self.ts = self.fk.load("ecentric_workspace.pm.api.timesheet")
        self.fk.module.response = {}
        self.proj("P1", project_name="Andros")
        F.task(self.fk, "T1", subject="Viết báo cáo", project="P1")
        F.task(self.fk, "T2", subject="Họp khách", project="P1")
        logs = [(F.ALICE, "T1", 3.5, "2026-10-14"), (F.ALICE, "T2", 1.0, "2026-10-15"),
                (F.ALICE, "T1", 2.0, "2026-10-15"), (F.BOB, "T2", 4.0, "2026-10-15")]
        for i in range(9):
            logs.append(("p%d@ec.vn" % i, "T2", 0.5, "2026-10-16"))
        for i, (u, t, h, d) in enumerate(logs):
            self.fk.add("Timesheet Detail", name="TD%02d" % i, parent="TS%02d" % i, task=t, project="P1",
                        from_time=d + " 09:00:00", hours=h, description="log %d" % i, owner=u)

    def test_report_keeps_old_keys_and_adds_new(self):
        self.me(F.LEADER)
        r = self.ts.report()
        for k in ("rows", "total_hours", "by_day", "by_week", "by_month"):
            self.assertIn(k, r)
        self.assertEqual(len(r["rows"]), 13)
        self.assertAlmostEqual(r["total_hours"], 15.0)
        self.assertEqual(r["top_tasks"][0], {"task": "T2", "subject": "Họp khách", "hours": 9.5,
                                             "project": "P1", "project_name": "Andros"})
        self.assertEqual(r["top_tasks"][1]["subject"], "Viết báo cáo")
        self.assertEqual(r["by_project"], [{"project": "P1", "project_name": "Andros", "hours": 15.0}])

    def test_people_paging(self):
        self.me(F.LEADER)
        r = self.ts.report()
        self.assertEqual((len(r["people"]), r["people_total"]), (7, 11))
        a = r["people"][0]
        self.assertEqual((a["user"], a["full_name"], a["hours"], a["logs"], a["days"]), (F.ALICE, "Alice", 6.5, 3, 2))
        self.assertEqual(a["top_tasks"][0], {"task": "T1", "subject": "Viết báo cáo", "hours": 5.5})
        self.assertEqual(r["people"][1]["user"], F.BOB)
        r2 = self.ts.report(people_start=7, people_len=7)
        self.assertEqual((len(r2["people"]), r2["people_total"]), (4, 11))

    def test_non_manager_sees_only_own(self):
        self.me(F.ALICE)
        r = self.ts.report(user=F.BOB)   # user filter ignored for non-managers
        self.assertEqual({x["owner"] for x in r["rows"]}, {F.ALICE})
        self.assertEqual((r["people_total"], r["people"][0]["user"]), (1, F.ALICE))

    def _stub_xlsx(self):
        captured = {}
        mod = types.ModuleType("frappe.utils.xlsxutils")

        class _B(object):
            def __init__(self, data):
                self.data = data

            def getvalue(self):
                return b"XLSX"

        def make_xlsx(data, sheet_name, **kw):
            captured["data"], captured["sheet"] = data, sheet_name
            return _B(data)
        mod.make_xlsx = make_xlsx
        sys.modules["frappe.utils.xlsxutils"] = mod
        return captured

    def test_export_xlsx(self):
        cap = self._stub_xlsx()
        self.me(F.LEADER)
        self.ts.export_xlsx(from_date="2026-10-14", to_date="2026-10-15")
        resp = self.fk.module.response
        self.assertEqual((resp["type"], resp["filecontent"], resp["filename"]),
                         ("binary", b"XLSX", "timesheet_2026-10-14_2026-10-15.xlsx"))
        data = cap["data"]
        self.assertEqual(data[0][:4], ["Ngày", "Người", "Email", "Dự án"])
        self.assertEqual(len(data), 1 + 4)
        self.assertIn(["2026-10-15", "Bob", F.BOB, "Andros", "Họp khách", "T2", 4.0, "log 3"], data)

    def test_export_xlsx_permission(self):
        cap = self._stub_xlsx()
        self.me(F.ALICE)
        self.ts.export_xlsx(user=F.BOB)
        self.assertEqual({row[2] for row in cap["data"][1:]}, {F.ALICE})
        self.me("nopm@ec.vn")
        with self.assertRaises(F.PermissionError):
            self.ts.export_xlsx()


if __name__ == "__main__":
    unittest.main()

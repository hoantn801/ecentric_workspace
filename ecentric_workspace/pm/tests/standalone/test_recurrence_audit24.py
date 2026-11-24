# -*- coding: utf-8 -*-
"""Rà soát 24/11/2026 - luật Lặp lại (pm.api.recurrence) trên số liệu live.

  R1 luật không người nhận (template_assignees []) -> việc không vào hàng đợi của ai
     -> giao cho chủ luật.
  R2 template_duration_days = 0 -> việc không hạn -> hạn = ngày bắt đầu + số ngày (0 = trong ngày).
  R3 luật gắn dự án đã quá expected_end_date -> ERPNext InvalidDates mỗi đêm, luật kẹt
     -> nới hạn dự án (quyền của chủ luật) + ghi Comment trên dự án.
  R4 lỗi kiểm tra/quyền của MỘT luật không được giữ luật kẹt mãi, không chặn luật khác.
  R5 luật tụt lại N kỳ -> chỉ tạo kỳ hiện tại (không đẻ việc đã trễ mỗi đêm).
  R6 tạo trùng luật (cùng chủ, tên, tần suất, dự án, Active) -> báo rõ.
Fake 'today' = 2026-10-16 (_pm_fake)."""
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
        self.fk.doctypes.add("PM Recurrence")
        self.rec = self.fk.load("ecentric_workspace.pm.api.recurrence")

    def rule(self, name, owner=F.GIVER, assignees=(), nrd="2026-10-16", project=None, dur=0,
             subject=None, **kw):
        row = dict(name=name, owner=owner, template_subject=subject or ("Luat " + name),
                   frequency="Daily", interval=1, status="Active", start_date="2026-10-01",
                   next_run_date=nrd, template_assignees=json.dumps(list(assignees)),
                   template_duration_days=dur, project=project, occurrences_done=0,
                   max_occurrences=0)
        row.update(kw)
        return self.fk.add("PM Recurrence", **row)

    def made(self):
        return [self.fk.row("Task", n) for dt, n in self.fk.inserted if dt == "Task"]


class TestOccurrenceShape(Base):
    def test_R1_unassigned_rule_goes_to_owner(self):
        self.rule("R1")
        self.rec.run_due()
        t = self.made()[0]
        self.assertEqual(json.loads(t["_assign"]), [F.GIVER])
        self.assertEqual(t["owner"], F.GIVER)

    def test_R1_template_assignees_kept(self):
        self.rule("R1b", assignees=[F.ALICE])
        self.rec.run_due()
        self.assertEqual(json.loads(self.made()[0]["_assign"]), [F.ALICE])

    def test_R2_due_date_same_day_when_duration_zero(self):
        self.rule("R2")
        self.rec.run_due()
        t = self.made()[0]
        self.assertEqual((str(t["exp_start_date"]), str(t["exp_end_date"])),
                         ("2026-10-16", "2026-10-16"))

    def test_R2_due_date_plus_duration(self):
        self.rule("R2b", dur=3)
        self.rec.run_due()
        self.assertEqual(str(self.made()[0]["exp_end_date"]), "2026-10-19")


class TestAssigneeLeft(Base):
    def test_R1_disabled_assignee_falls_back_to_owner(self):
        self.fk.row("User", F.ALICE)["enabled"] = 0
        self.rule("R1c", assignees=[F.ALICE])
        self.rec.run_due()
        self.assertEqual(json.loads(self.made()[0]["_assign"]), [F.GIVER])


class TestScheduleEdit(Base):
    def test_R7_moving_start_date_moves_next_run(self):
        self.fk.set_user(F.GIVER)
        r = self.rec.create(subject="Hop thang", frequency="Daily")
        self.assertEqual(r["next_run_date"], "2026-10-16")
        r = self.rec.update_template(r["name"], start_date="2026-11-02")
        self.assertEqual(r["next_run_date"], "2026-11-02")

    def test_R7_template_only_edit_keeps_next_run(self):
        self.fk.set_user(F.GIVER)
        r = self.rec.create(subject="Hop", frequency="Daily", start_date="2026-10-20")
        r = self.rec.update_template(r["name"], description="moi")
        self.assertEqual(r["next_run_date"], "2026-10-20")


class TestExpiredProject(Base):
    def setUp(self):
        super(TestExpiredProject, self).setUp()

        def erpnext_dates(doc, ev):   # ERPNext Task.validate_parent_project_dates (simplified)
            if doc.get("doctype") != "Task" or not doc.get("project"):
                return
            pend = self.fk.row("Project", doc["project"]).get("expected_end_date")
            for f in ("exp_start_date", "exp_end_date"):
                if pend and doc.get(f) and str(doc[f])[:10] > str(pend)[:10]:
                    raise self.fk.module.ValidationError("InvalidDates " + f)
        self.fk.hooks["Task"] = [erpnext_dates]

    def test_R3_project_widened_and_task_created(self):
        self.fk.add("Project", name="PROJ-0050", owner=F.GIVER, expected_start_date="2026-09-01",
                    expected_end_date="2026-10-01")
        self.rule("R3", project="PROJ-0050", nrd="2026-10-16", frequency="Weekly",
                  weekly_days="[4]")
        self.rec.run_due()
        self.assertEqual(len(self.made()), 1)
        self.assertEqual(str(self.fk.row("Project", "PROJ-0050")["expected_end_date"]), "2026-10-16")
        r = self.fk.row("PM Recurrence", "R3")
        self.assertEqual((r["occurrences_done"], str(r["next_run_date"])), (1, "2026-10-23"))
        self.assertTrue(self.fk.db.t("Comment"), "widening must leave a trace on the project")

    def test_R4_failing_rule_moves_on_and_does_not_block_others(self):
        # owner cannot open the project (not owner, no task there) -> PermissionError in widening
        self.fk.add("Project", name="PROJ-X", owner=F.LEADER, expected_end_date="2026-10-01")
        self.rule("BAD", owner=F.ALICE, project="PROJ-X")
        self.rule("GOOD", owner=F.BOB)
        self.rec.run_due()
        bad = self.fk.row("PM Recurrence", "BAD")
        self.assertEqual(str(bad["next_run_date"]), "2026-10-17")     # not stuck on 16/10
        self.assertEqual(bad["occurrences_done"], 0)
        self.assertEqual(self.fk.row("PM Recurrence", "GOOD")["occurrences_done"], 1)
        self.assertTrue(any("BAD" in str(e) for e in self.fk.errors))   # error names the rule


class TestCatchUp(Base):
    def test_R5_behind_rule_makes_only_today(self):
        self.rule("R5", nrd="2026-10-10")
        self.rec.run_due()
        made = self.made()
        self.assertEqual([str(t["exp_start_date"]) for t in made], ["2026-10-16"])
        self.assertEqual(str(self.fk.row("PM Recurrence", "R5")["next_run_date"]), "2026-10-17")

    def test_R5_respects_end_date(self):
        self.rule("R5e", nrd="2026-10-10", end_date="2026-10-12")
        self.rec.run_due()
        self.assertEqual([str(t["exp_start_date"]) for t in self.made()], ["2026-10-12"])
        self.assertEqual(self.fk.row("PM Recurrence", "R5e")["status"], "Completed")


class TestDuplicate(Base):
    def test_R6_same_rule_twice_is_refused(self):
        self.fk.set_user(F.GIVER)
        first = self.rec.create(subject="Daily catchup", frequency="Daily")
        with self.assertRaises(self.fk.module.DuplicateEntryError) as cm:
            self.rec.create(subject="  daily   CATCHUP ", frequency="Daily")
        self.assertIn(first["name"], str(cm.exception))

    def test_R6_other_frequency_or_cancelled_is_fine(self):
        self.fk.set_user(F.GIVER)
        a = self.rec.create(subject="Bao cao", frequency="Daily")
        self.rec.create(subject="Bao cao", frequency="Weekly")
        self.rec.cancel(a["name"])
        self.rec.create(subject="Bao cao", frequency="Daily")      # old one cancelled -> ok
        self.fk.set_user(F.ALICE)
        self.rec.create(subject="Bao cao", frequency="Weekly")     # other owner -> ok


class TestExistingDuplicates(Base):
    """R8: duplicates already on live (hoang.le 4x "Daily catchup") - one task a day, not four."""

    def test_R8_same_people_only_first_rule_creates(self):
        for n in ("D1", "D2", "D3"):
            self.rule(n, subject="Daily catchup")
        self.rec.run_due()
        self.assertEqual(len(self.made()), 1)
        for n in ("D1", "D2", "D3"):   # the others still move on (not stuck, not deleted)
            self.assertEqual(str(self.fk.row("PM Recurrence", n)["next_run_date"])[:10], "2026-10-17")
            self.assertEqual(self.fk.row("PM Recurrence", n)["status"], "Active")

    def test_R8_different_people_are_not_duplicates(self):
        self.rule("E1", subject="Doc dashboard")
        self.rule("E2", subject="Doc dashboard", assignees=[F.ALICE])
        self.rec.run_due()
        self.assertEqual(sorted(json.loads(t["_assign"])[0] for t in self.made()), sorted([F.GIVER, F.ALICE]))

    def test_R8_create_allows_same_name_for_other_person(self):
        self.fk.set_user(F.GIVER)
        self.rec.create(subject="Bao cao ngay", frequency="Daily", assignees=json.dumps([F.ALICE]))
        self.rec.create(subject="Bao cao ngay", frequency="Daily", assignees=json.dumps([F.BOB]))
        with self.assertRaises(Exception):
            self.rec.create(subject="bao  cao NGAY", frequency="Daily", assignees=json.dumps([F.ALICE]))


class TestNotify(Base):
    def test_owner_not_notified_for_own_task_but_told_when_given_away(self):
        self.rule("N1")                         # goes to the owner himself
        self.rule("N2", assignees=[F.ALICE])    # goes to Alice
        self.rec.run_due()
        mine = [n for n in self.fk.notifications if n["user"] == F.GIVER]
        self.assertEqual(len(mine), 1)
        self.assertIn("Việc lặp lại mới đã giao", mine[0]["subject"])


class TestClosePrevious(Base):
    """PO 24/11: Daily rule - the previous occurrence nobody touched is cancelled when the new one comes."""

    def _prev(self, name="OLD1", **kw):
        F.task(self.fk, name, owner=F.GIVER, assign=[F.GIVER], state=kw.pop("state", "Backlog"), end="2026-10-15", **kw)
        return name

    def test_untouched_previous_daily_is_cancelled_with_note(self):
        self.rule("C1", last_task=self._prev())
        self.rec.run_due()
        self.assertEqual(self.fk.row("Task", "OLD1")["workflow_state"], "Cancelled")
        notes = [d for d in self.fk.db.t("Comment").values() if d.get("reference_name") == "OLD1" and d.get("comment_type") == "Info"]
        self.assertTrue(notes and "Tự huỷ" in notes[0]["content"])

    def test_started_previous_is_kept(self):
        self.rule("C2", last_task=self._prev(state="In Progress"))
        self.rec.run_due()
        self.assertEqual(self.fk.row("Task", "OLD1")["workflow_state"], "In Progress")

    def test_commented_previous_is_kept(self):
        self.rule("C3", last_task=self._prev())
        self.fk.add("Comment", name="CM1", reference_doctype="Task", reference_name="OLD1", comment_type="Comment", content="x")
        self.rec.run_due()
        self.assertEqual(self.fk.row("Task", "OLD1")["workflow_state"], "Backlog")

    def test_weekly_rule_keeps_previous(self):
        self.rule("C4", last_task=self._prev(), frequency="Weekly", weekly_days=json.dumps([4]))
        self.rec.run_due()
        self.assertEqual(self.fk.row("Task", "OLD1")["workflow_state"], "Backlog")


if __name__ == "__main__":
    unittest.main()

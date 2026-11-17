# -*- coding: utf-8 -*-
"""Việc cần làm (15/11/2026): pm.api.queue - ONE ordering rule shared by /pm, Teams digest, MCP.
Fake 'now' = Fri 2026-10-16 10:00 (_pm_fake)."""
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
        self.q = self.fk.load("ecentric_workspace.pm.api.queue")

    def me(self, u=F.ALICE):
        self.fk.set_user(u)


class TestRule(Base):
    def test_buckets_and_order(self):
        A = [F.ALICE]
        F.task(self.fk, "LATE_LOW", assign=A, end="2026-10-14", priority="Low")
        F.task(self.fk, "LATE_URG", assign=A, end="2026-10-15", priority="Urgent")
        F.task(self.fk, "TODAY_9H", assign=A, end="2026-10-16 00:00:00", pm_end_time="9:00:00", priority="Low")  # passed -> late
        F.task(self.fk, "TODAY_MED", assign=A, end="2026-10-16", priority="Medium")
        F.task(self.fk, "TODAY_HIGH_17", assign=A, end="2026-10-16", pm_end_time="17:00:00", priority="High")
        F.task(self.fk, "TODAY_HIGH_11", assign=A, end="2026-10-16", pm_end_time="11:00:00", priority="High")
        F.task(self.fk, "TOMORROW", assign=A, end="2026-10-17", priority="Low")
        F.task(self.fk, "SUNDAY", assign=A, end="2026-10-18", priority="Urgent")
        F.task(self.fk, "NEXT_WEEK", assign=A, end="2026-10-19", priority="Urgent")
        F.task(self.fk, "NODUE_URG", assign=A, priority="Urgent")
        F.task(self.fk, "MIDNIGHT", assign=A, end="2026-10-16", pm_end_time="0:00:00", priority="Low")   # 0:00 = no time
        F.task(self.fk, "DONE", assign=A, end="2026-10-10", state="Done")
        F.task(self.fk, "OTHER", assign=[F.BOB], end="2026-10-10")
        F.task(self.fk, "SUBSTR", assign=["xalice@ec.vn"], end="2026-10-10")
        self.me()
        out = self.q.list()
        names = [r["name"] for r in out["rows"]]
        self.assertEqual(names, ["LATE_URG", "LATE_LOW", "TODAY_9H", "TODAY_HIGH_11", "TODAY_HIGH_17", "TODAY_MED",
                                 "MIDNIGHT", "TOMORROW", "SUNDAY", "NEXT_WEEK", "NODUE_URG"])
        b = {r["name"]: r["bucket"] for r in out["rows"]}
        self.assertEqual((b["TODAY_9H"], b["MIDNIGHT"], b["SUNDAY"], b["NEXT_WEEK"], b["NODUE_URG"]),
                         ("late", "today", "week", "later", "none"))
        self.assertEqual([r["rank"] for r in out["rows"]], list(range(1, 12)))
        self.assertEqual(out["counts"], {"late": 3, "today": 4, "tomorrow": 1, "week": 1, "later": 1, "none": 1, "stale": 0})
        m = [r for r in out["rows"] if r["name"] == "MIDNIGHT"][0]
        self.assertEqual((m["due"], m["due_time"]), ("2026-10-16", None))

    def test_late_by_hours_flips_bucket(self):
        F.task(self.fk, "T", assign=[F.ALICE], end="2026-10-16", pm_end_time="10:30:00")
        self.me()
        self.assertEqual(self.q.list()["rows"][0]["bucket"], "today")
        self.fk.advance(hours=1)
        self.assertEqual(self.q.list()["rows"][0]["bucket"], "late")

    def test_personal_log_hidden_by_default(self):
        self.fk.add("Project", name="WL", project_name="Nhat ky", ec_personal_log=1)
        F.task(self.fk, "LOG", owner=F.ALICE, assign=[F.ALICE], project="WL", end="2026-10-16")
        F.task(self.fk, "REAL", assign=[F.ALICE], end="2026-10-16")
        self.me()
        out = self.q.list()
        self.assertEqual(([r["name"] for r in out["rows"]], out["personal_hidden"]), (["REAL"], 1))
        self.assertEqual(len(self.q.list(include_personal=1)["rows"]), 2)


class TestShape(Base):
    def test_row_fields_giver_and_self(self):
        self.fk.add("Project", name="P1", project_name="ANDROS")
        F.task(self.fk, "G", owner=F.GIVER, assign=[F.ALICE], project="P1", end="2026-10-17", priority="High")
        F.task(self.fk, "S", owner=F.ALICE, assign=[F.ALICE], end="2026-10-17")
        self.me()
        rows = {r["name"]: r for r in self.q.list()["rows"]}
        g, s = rows["G"], rows["S"]
        self.assertEqual((g["giver"], g["giver_name"], g["self"], g["project_name"], g["priority_rank"]),
                         (F.GIVER, "Gia Ver", False, "ANDROS", 3))
        self.assertTrue(s["self"])
        self.assertNotIn("_assign", g)

    def test_asks_listed_on_me_tab(self):
        F.task(self.fk, "REQ", owner=F.GIVER, assign=[], state="Backlog")
        self.fk.add("PM Assignment Request", name="AR1", task="REQ", recipient=F.ALICE, requested_by=F.GIVER,
                    status="Pending", kind="Assignment", proposed_end="2026-10-20 00:00:00")
        self.me()
        self.assertEqual([a["request"] for a in self.q.list()["asks"]], ["AR1"])
        self.assertEqual(self.q.list(tab="give")["asks"], [])


class TestGiven(Base):
    def test_given_tab_others_only_with_opened_flag(self):
        F.task(self.fk, "TO_BOB", owner=F.ALICE, assign=[F.BOB], end="2026-10-15")
        F.task(self.fk, "TO_ME", owner=F.ALICE, assign=[F.ALICE], end="2026-10-15")
        F.task(self.fk, "BOB_DONE", owner=F.ALICE, assign=[F.BOB], state="Done")
        F.task(self.fk, "NOBODY", owner=F.ALICE, assign=[], end="2026-10-15")
        self.me()
        out = self.q.list(tab="give")
        self.assertEqual([r["name"] for r in out["rows"]], ["TO_BOB"])
        r = out["rows"][0]
        self.assertEqual((r["assignees"][0]["user"], r["assignees"][0]["opened"], r["unopened"]), (F.BOB, False, True))
        self.fk.add("PM Task Seen", name="TO_BOB::" + F.BOB, task="TO_BOB", user=F.BOB)
        self.assertFalse(self.q.list(tab="give")["rows"][0]["unopened"])

    def test_requires_pm_access(self):
        self.me("nopm@ec.vn")
        with self.assertRaises(F.PermissionError):
            self.q.list()


class TestDigest(Base):
    def test_off_by_default(self):
        self.assertEqual(self.q.morning_digest(), {"skipped": "disabled"})

    def test_one_message_per_person_with_top3(self):
        self.fk.module.get_conf = lambda: {"ec_pm_morning_digest": 1}
        F.task(self.fk, "A1", assign=[F.ALICE], end="2026-10-15", priority="Urgent", subject="Bao gia")
        F.task(self.fk, "A2", assign=[F.ALICE], end="2026-10-16", subject="Chot GMV")
        F.task(self.fk, "B1", assign=[F.BOB], end="2026-10-30")      # not due -> no message for Bob
        sent = []
        ev = self.fk.load("ecentric_workspace.notification_center.events") if False else None
        import types
        m = types.ModuleType("ecentric_workspace.notification_center.events")
        m.publish_notification_event = lambda et, u, title, msg, **k: sent.append((et, u, title, msg, k.get("dedupe_key"), k.get("action_url")))
        sys.modules["ecentric_workspace.notification_center.events"] = m
        nc = sys.modules.get("ecentric_workspace.notification_center") or types.ModuleType("ecentric_workspace.notification_center")
        nc.events = m
        sys.modules["ecentric_workspace.notification_center"] = nc
        out = self.q.morning_digest()
        self.assertEqual(out, {"sent": 1})
        et, u, title, msg, key, url = sent[0]
        self.assertEqual((et, u, url, key), ("task_due_soon", F.ALICE, "/pm#mywork", "pm_digest|%s|2026-10-16" % F.ALICE))
        self.assertIn("2 việc", title)
        self.assertIn("1. Bao gia", msg)


if __name__ == "__main__":
    unittest.main()

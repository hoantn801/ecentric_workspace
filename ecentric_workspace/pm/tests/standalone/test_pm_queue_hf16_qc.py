# -*- coding: utf-8 -*-
"""QC reviewer - hotfix 16 (queue stale / bulk / follow), 17/11/2026. Each finding was fixed in
queue_actions.bulk; these tests pin the fixed behaviour. test_doc_* pin a behaviour kept on purpose
(digest for people with only stale work = PO decision; MCP shape unchanged).
Fake 'now' = Fri 2026-10-16 10:00."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.q = self.fk.load("ecentric_workspace.pm.api.queue")
        self.qa = self.fk.load("ecentric_workspace.pm.api.queue_actions")
        self.tasks = self.fk.load("ecentric_workspace.pm.api.tasks")
        self.fk.set_user(F.ALICE)


class TestFormDictLeak(Base):
    """bulk -> tasks.update reads frappe.local.form_dict (_sent_fields) of the OUTER bulk request:
    any extra key there (assignee / exp_start_date / pm_start_time) is treated as an explicit clear."""

    def test_extra_key_in_bulk_request_unassigns_everyone(self):
        F.task(self.fk, "MINE", owner=F.ALICE, assign=[F.ALICE, F.BOB], end="2026-09-01", start="2026-08-20")
        self.fk.module.local.form_dict = {"cmd": "x.bulk", "action": "move", "names": '["MINE"]',
                                          "due": "2026-10-20", "assignee": "", "exp_start_date": ""}
        out = self.qa.bulk("move", '["MINE"]', due="2026-10-20")
        self.assertEqual(out["ok"], ["MINE"])
        row = self.fk.row("Task", "MINE")
        # EXPECTED: only the due date changes. ACTUAL: assignees removed + start date wiped.
        self.assertEqual(sorted(__import__("json").loads(row["_assign"] or "[]")), [F.ALICE, F.BOB])
        self.assertEqual(str(row.get("exp_start_date") or "")[:10], "2026-08-20")


class TestDeadlockInsideBulk(Base):
    """tasks.update is @retry_on_deadlock: on QueryDeadlockError it calls frappe.db.rollback()
    (FULL rollback) and retries. Inside bulk that silently undoes every task processed before,
    yet bulk still reports them in `ok`."""

    def test_full_rollback_mid_bulk_but_earlier_tasks_reported_ok(self):
        F.task(self.fk, "T1", owner=F.ALICE, assign=[F.ALICE], end="2026-09-01")
        F.task(self.fk, "T2", owner=F.ALICE, assign=[F.ALICE], end="2026-09-01")
        dl = sys.modules["ecentric_workspace.pm.deadlock"]
        dl.time = types.SimpleNamespace(sleep=lambda s: None)
        orig = self.tasks._clean_schedule
        hit = {"n": 0}

        def flaky(*a, **k):
            if self.tasks.frappe.local.__dict__.get("_cur") == "T2" and hit["n"] == 0:
                hit["n"] += 1
                raise self.fk.module.exceptions.QueryDeadlockError("1213")
            return orig(*a, **k)
        orig_update = self.tasks.update.__wrapped__ if hasattr(self.tasks.update, "__wrapped__") else None
        self.assertIsNotNone(orig_update, "update is expected to be wrapped by retry_on_deadlock")
        real_get_doc = self.fk.module.get_doc

        def get_doc(dt, name=None, *a, **k):
            if dt == "Task" and isinstance(name, str):
                self.tasks.frappe.local._cur = name
            return real_get_doc(dt, name, *a, **k)
        self.fk.module.get_doc = get_doc
        self.tasks._clean_schedule = flaky
        out = None
        try:
            with self.assertRaises(Exception) as cm:
                out = self.qa.bulk("move", ["T1", "T2"], due="2026-10-20")
            self.assertIn("chưa lưu việc nào", str(cm.exception))
        finally:
            self.tasks._clean_schedule = orig
            self.fk.module.get_doc = real_get_doc
        # fixed: no inner retry (it rolled back ALL); a deadlock stops the batch, rolls back and SAYS so
        self.assertIsNone(out)
        self.assertIn(None, getattr(self.fk.db, "rolled_back", []))


class TestSplitParentMove(Base):
    def test_split_parent_is_skipped_with_reason(self):
        F.task(self.fk, "P", owner=F.ALICE, assign=[], end="2026-09-01", split=1)
        F.task(self.fk, "C1", owner=F.ALICE, assign=[F.BOB], end="2026-09-01", parent_task="P")
        out = self.qa.bulk("move", ["P"], due="2026-10-30")
        self.assertEqual(out["ok"], [])
        self.assertEqual(out["skipped"][0]["reason"], "split")
        self.assertEqual(str(self.fk.row("Task", "P")["exp_end_date"])[:10], "2026-09-01")


class TestPolicyOracle(Base):
    def test_outsider_cannot_tell_existing_from_missing(self):
        F.task(self.fk, "SECRET", owner=F.GIVER, assign=[F.BOB], end="2026-09-01")
        self.fk.set_user(F.OUTSIDER)
        out = self.qa.bulk("move", ["SECRET", "NOPE"], due="2026-10-20")
        r = {s["name"]: s["reason"] for s in out["skipped"]}
        self.assertEqual(r, {"SECRET": "not_found", "NOPE": "not_found"})


class TestBlockedMessage(Base):
    def test_blocked_reason_is_human_text(self):
        F.task(self.fk, "PAR", owner=F.ALICE, assign=[F.ALICE], end="2026-09-01")
        F.task(self.fk, "KID", owner=F.ALICE, assign=[F.ALICE], parent_task="PAR")
        out = self.qa.bulk("done", ["PAR"])
        self.assertEqual(out["skipped"][0]["reason"], "blocked")
        self.assertEqual(out["skipped"][0]["message"], "Còn 1 việc con chưa xong.")


class TestLimits(Base):
    def test_server_takes_at_most_50_per_call(self):   # the screen sends chunks of 50 (progress)
        for i in range(51):
            F.task(self.fk, "S%03d" % i, owner=F.ALICE, assign=[F.ALICE], end="2026-09-01")
        stale = [r["name"] for r in self.q.list()["rows"] if r["bucket"] == "stale"]
        self.assertEqual(len(stale), 51)
        with self.assertRaises(Exception):
            self.qa.bulk("move", stale, due="2026-10-20")
        self.assertEqual(len(self.qa.bulk("move", stale[:50], due="2026-10-20")["ok"]), 50)


class TestDigestOnlyStale(Base):
    def _hook(self):
        sent = []
        self.fk.module.get_conf = lambda: {"ec_pm_morning_digest": 1}
        m = types.ModuleType("ecentric_workspace.notification_center.events")
        m.publish_notification_event = lambda et, u, title, msg, **k: sent.append((u, title, msg))
        sys.modules["ecentric_workspace.notification_center.events"] = m
        nc = sys.modules.get("ecentric_workspace.notification_center") or types.ModuleType("ecentric_workspace.notification_center")
        nc.events = m
        sys.modules["ecentric_workspace.notification_center"] = nc
        return sent

    def test_doc_person_with_only_stale_gets_no_digest(self):
        sent = self._hook()
        F.task(self.fk, "OLD1", assign=[F.ALICE], end="2026-08-01")
        F.task(self.fk, "OLD2", assign=[F.ALICE], end="2026-08-02")
        self.assertEqual(self.q.morning_digest(), {"sent": 0})   # was 1 before hf16; stale never surfaced

    def test_doc_asks_only_branch_hides_stale(self):
        sent = self._hook()
        F.task(self.fk, "OLD1", assign=[F.ALICE], end="2026-08-01")
        F.task(self.fk, "ASKED", owner=F.GIVER, assign=[])
        self.fk.add("PM Assignment Request", name="R1", task="ASKED", requested_by=F.GIVER,
                    recipient=F.ALICE, status="Pending", kind="Assignment")
        self.q.morning_digest()
        self.assertEqual(len(sent), 1)
        self.assertNotIn("tồn đọng", sent[0][2])


class TestMcp(Base):
    def test_doc_mcp_ranks_stale_and_has_no_follow(self):
        F.task(self.fk, "OLD", assign=[F.ALICE], end="2026-08-01", priority="Urgent")
        F.task(self.fk, "NOW", assign=[F.ALICE], end="2026-10-16")
        rows = self.q.list()["rows"]
        self.assertEqual([(r["name"], r["rank"]) for r in rows], [("NOW", 1), ("OLD", 2)])  # stale gets a "làm thứ" rank


if __name__ == "__main__":
    unittest.main()

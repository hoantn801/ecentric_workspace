# Copyright (c) 2026, eCentric and contributors
"""Shared Action feed service (Phase 1a) -- bench-free (frappe stubbed).

Covers classification boundaries, deterministic ordering, cursor pagination,
dedup + terminal filtering across Approval/PM/WTU, PM/approval due
derivation, backward-compatible get_action_items envelope, session scope,
and the PM terminal ToDo-close hook.
"""
import datetime
import io
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)


# ----------------------------- fake frappe --------------------------------- #
class _FakeDB:
    def __init__(self):
        self.todo_rows = []
        self.get_value_map = {}          # (doctype, name, field) -> value
        self.set_calls = []              # (doctype, name, field, value)
        self.open_task_todos = []        # for pm close tests
    def sql(self, q, params, as_dict=False):
        return list(self.todo_rows)
    def get_value(self, doctype, name, field=None, as_dict=False):
        if isinstance(field, (list, tuple)):
            return {f: self.get_value_map.get((doctype, name, f)) for f in field}
        return self.get_value_map.get((doctype, name, field))
    def set_value(self, doctype, name, field, value, update_modified=True):
        self.set_calls.append((doctype, name, field, value))
    def exists(self, *a, **k):
        return True
    def table_exists(self, *a, **k):
        return True


class _FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__("frappe")
        self.db = _FakeDB()
        self.session = types.SimpleNamespace(user="u@e.c")
        self.flags = types.SimpleNamespace(in_install=False, in_migrate=False, in_patch=False)
        self.response = {}
        self.getall_map = {}             # doctype -> list of dict rows (filtered by name/ref)
        self.utils = types.SimpleNamespace(
            getdate=lambda *a: datetime.date(2026, 7, 24),
            now_datetime=lambda: "2026-07-24 10:00:00")
        self.whitelist = lambda *a, **k: (lambda f: f)
        self._ = lambda s: s
    def get_all(self, doctype, filters=None, fields=None, limit=None, ignore_permissions=False,
                order_by=None, limit_page_length=None):
        rows = self.getall_map.get(doctype, [])
        f = filters or {}
        out = []
        for r in rows:
            ok = True
            for k, v in f.items():
                if isinstance(v, list) and v and v[0] == "in":
                    if r.get(k) not in v[1]:
                        ok = False; break
                elif r.get(k) != v:
                    ok = False; break
            if ok:
                out.append(dict(r))
        if limit:
            out = out[:limit]
        return out
    def log_error(self, *a, **k):
        pass
    def get_traceback(self):
        return ""
    def logger(self):
        return types.SimpleNamespace(info=lambda *a, **k: None)


def _install(fake, purge=True):
    sys.modules["frappe"] = fake
    if purge:
        for m in list(sys.modules):
            if m.startswith("ecentric_workspace.action_center") or m == "ecentric_workspace.pm.permissions":
                sys.modules.pop(m, None)


FK = _FakeFrappe(); _install(FK)
from ecentric_workspace.action_center import feed          # noqa: E402
from ecentric_workspace.action_center import api as ac_api  # noqa: E402

TODAY = datetime.date(2026, 7, 24)


# ------------------------------- pure logic -------------------------------- #
class TestClassify(unittest.TestCase):
    def test_boundaries(self):
        self.assertIsNone(feed.classify("2026-07-24", TODAY, active=False, terminal=True))
        self.assertEqual(feed.classify("2026-07-23", TODAY, False, False), "overdue")
        self.assertEqual(feed.classify("2026-07-24", TODAY, False, False), "act_now")   # today
        self.assertEqual(feed.classify("2026-07-25", TODAY, False, False), "upcoming")
        self.assertEqual(feed.classify("", TODAY, active=True, terminal=False), "act_now")   # active undated
        self.assertEqual(feed.classify("", TODAY, active=False, terminal=False), "undated")
        # terminal always excluded regardless of due/active
        self.assertIsNone(feed.classify("2026-07-25", TODAY, active=True, terminal=True))

    def test_active_does_not_override_a_real_date(self):
        # active only promotes UNDATED items; a future-dated active item stays upcoming
        self.assertEqual(feed.classify("2026-07-25", TODAY, active=True, terminal=False), "upcoming")


class TestOrderingAndCursor(unittest.TestCase):
    def test_deterministic_order(self):
        items = [
            {"bucket": "upcoming", "due_at": "2026-07-26", "source_type": "task", "todo_name": "t1", "_creation": "1"},
            {"bucket": "overdue", "due_at": "2026-07-20", "source_type": "task", "todo_name": "t2", "_creation": "2"},
            {"bucket": "act_now", "due_at": "2026-07-24", "source_type": "task", "todo_name": "t3", "_creation": "3"},
            {"bucket": "act_now", "due_at": "", "source_type": "approval", "todo_name": "t4", "_creation": "4"},
            {"bucket": "act_now", "due_at": "2026-07-24", "source_type": "approval", "todo_name": "t5", "_creation": "5"},
        ]
        order = [i["todo_name"] for i in feed.order_items(items)]
        # overdue first; within act_now: dated (24th) before undated; approval before task on ties
        self.assertEqual(order[0], "t2")                       # overdue
        self.assertEqual(order[1], "t5")                       # act_now dated, approval prio
        self.assertEqual(order[2], "t3")                       # act_now dated, task
        self.assertEqual(order[3], "t4")                       # act_now undated last
        self.assertEqual(order[4], "t1")                       # upcoming last

    def test_order_never_uses_modified(self):
        src = io.open(os.path.join(APP, "action_center", "feed.py"), encoding="utf-8").read()
        self.assertNotIn("modified", src.split("def _sort_key")[1].split("def ")[0])

    def test_cursor_roundtrip(self):
        self.assertEqual(feed.decode_cursor(feed.encode_cursor(40)), 40)
        self.assertEqual(feed.decode_cursor(None), 0)
        self.assertEqual(feed.decode_cursor("garbage!!"), 0)   # tamper -> 0, never crash


# --------------------------- feed integration ------------------------------ #
def _todo(name, rt, rn, date="", created="1", priority="Medium"):
    return {"name": name, "description": "d", "reference_type": rt, "reference_name": rn,
            "priority": priority, "modified": "2026-07-01", "creation": created,
            "date": date, "status": "Open"}


class TestBuildFeed(unittest.TestCase):
    def setUp(self):
        _install(FK, purge=False)
        FK.db = _FakeDB(); FK.getall_map = {}
        FK.session.user = "u@e.c"
        # resolve_item title lookups
        FK.db.get_value_map = {
            ("Weekly Team Update", "WTU-1", "week_label"): "2026-W30",
            ("Task", "TASK-1", "subject"): "Do X",
            ("Task", "TASK-DONE", "subject"): "Done X",
            ("PO Request", "PO-1", "title"): "PO one",
            ("PO Request", "PO-1", "name"): "PO-1",
        }

    def test_dedup_terminal_and_due_derivation(self):
        FK.db.todo_rows = [
            _todo("td-appr", "PO Request", "PO-1", created="1"),        # approval, active level w/ SLA
            _todo("td-appr2", "PO Request", "PO-1", created="1b"),      # DUP same doc -> engine idempotent normally; both counted here but same source_id
            _todo("td-task", "Task", "TASK-1", created="2"),            # PM active, due from exp_end_date
            _todo("td-taskdone", "Task", "TASK-DONE", created="3"),     # PM terminal -> excluded
            _todo("td-wtu", "Weekly Team Update", "WTU-1", date="2026-07-24", created="4"),  # today
            _todo("td-wtu-done", "Weekly Team Update", "WTU-2", date="2026-07-20", created="5"),  # terminal -> excluded
        ]
        FK.getall_map = {
            "EC Approval Request": [
                {"name": "REQ-1", "reference_name": "PO-1", "approval_status": "Pending"}],
            "EC Approval Request Level": [
                {"approval_request": "REQ-1", "level_status": "In Progress", "due_at": "2026-07-23 09:00:00"}],
            "Task": [
                {"name": "TASK-1", "workflow_state": "In Progress", "status": "Working", "exp_end_date": "2026-07-25"},
                {"name": "TASK-DONE", "workflow_state": "Done", "status": "Completed", "exp_end_date": "2026-07-10"}],
            "Weekly Team Update": [
                {"name": "WTU-1", "status": "Draft"},
                {"name": "WTU-2", "status": "Submitted"}],
        }
        res = feed.build_feed("u@e.c", limit=20)
        routes = {i["todo_name"]: i for i in res["items"]}
        # terminal excluded
        self.assertNotIn("td-taskdone", routes)
        self.assertNotIn("td-wtu-done", routes)
        # approval SLA due -> 07-23 < today -> overdue
        self.assertEqual(routes["td-appr"]["bucket"], "overdue")
        self.assertEqual(routes["td-appr"]["due_at"], "2026-07-23 09:00:00")
        # PM due from exp_end_date 07-25 -> upcoming (active, but dated future stays upcoming)
        self.assertEqual(routes["td-task"]["due_at"], "2026-07-25")
        self.assertEqual(routes["td-task"]["bucket"], "upcoming")
        # WTU today -> act_now
        self.assertEqual(routes["td-wtu"]["bucket"], "act_now")
        # counts over full feed
        self.assertEqual(res["counts"]["overdue"], 2)   # td-appr + td-appr2 (both PO-1 overdue)
        self.assertEqual(res["total"], res["counts"]["overdue"] + res["counts"]["act_now"]
                         + res["counts"]["upcoming"] + res["counts"]["undated"])

    def test_source_counts_across_full_feed(self):
        FK.db.todo_rows = [
            _todo("a", "PO Request", "PO-1", created="1"),      # approval
            _todo("b", "Task", "TASK-1", created="2"),          # pm
            _todo("c", "Weekly Team Update", "W1", date="2026-07-24", created="3"),  # weekly_update
            _todo("d", "", "", date="2026-07-24", created="4"),  # generic_todo
        ]
        FK.getall_map = {
            "EC Approval Request": [{"name": "R", "reference_name": "PO-1", "approval_status": "Pending"}],
            "EC Approval Request Level": [{"approval_request": "R", "level_status": "In Progress", "due_at": "2026-07-24 09:00"}],
            "Task": [{"name": "TASK-1", "workflow_state": "In Progress", "status": "Working", "exp_end_date": "2026-07-24"}],
            "Weekly Team Update": [{"name": "W1", "status": "Draft"}],
        }
        FK.db.get_value_map = {("Weekly Team Update", "W1", "week_label"): "W30"}
        res = feed.build_feed("u@e.c", limit=20)
        sc = res["source_counts"]
        self.assertEqual(sc, {"approval": 1, "pm": 1, "weekly_update": 1, "generic_todo": 1})
        # source_counts sums to total (full filtered feed, pre-pagination)
        self.assertEqual(sum(sc.values()), res["total"])
        # exposed by BOTH endpoints, same shape, no dup query
        r1 = ac_api.get_action_items()
        self.assertIn("source_counts", r1)
        r2 = ac_api.get_reminder_summary()
        self.assertEqual(r2["source_counts"], sc)

    def test_pagination_cursor(self):
        FK.db.todo_rows = [_todo("t%02d" % i, "", "", date="2026-07-2%d" % (i % 6), created="%02d" % i)
                           for i in range(25)]  # bare ToDos, undated? date set -> various buckets
        res1 = feed.build_feed("u@e.c", limit=10)
        self.assertEqual(res1["returned"], 10)
        self.assertIsNotNone(res1["next_cursor"])
        res2 = feed.build_feed("u@e.c", cursor=res1["next_cursor"], limit=10)
        self.assertEqual(res2["returned"], 10)
        # no overlap between page 1 and page 2
        p1 = {i["todo_name"] for i in res1["items"]}
        p2 = {i["todo_name"] for i in res2["items"]}
        self.assertEqual(p1 & p2, set())
        # counts identical across pages (full-feed counts)
        self.assertEqual(res1["counts"], res2["counts"])

    def test_limit_capped(self):
        FK.db.todo_rows = []
        self.assertEqual(feed.build_feed("u@e.c", limit=99999)["returned"], 0)
        # cap enforced internally
        self.assertLessEqual(feed.MAX_LIMIT, 100)


class TestApiBackwardCompat(unittest.TestCase):
    def setUp(self):
        _install(FK, purge=False)
        FK.db = _FakeDB(); FK.getall_map = {}; FK.session.user = "u@e.c"
        FK.db.todo_rows = [_todo("t1", "", "", date="2026-07-24", created="1")]

    def test_envelope_keys_unchanged(self):
        r = ac_api.get_action_items()
        for k in ("success", "count", "items", "counts", "generated_at"):
            self.assertIn(k, r)
        # additive pagination keys present but non-breaking
        for k in ("total", "returned", "next_cursor"):
            self.assertIn(k, r)
        self.assertTrue(r["success"])
        self.assertEqual(r["count"], len(r["items"]))

    def test_guest_rejected_and_session_scoped(self):
        FK.session.user = "Guest"
        r = ac_api.get_action_items()
        self.assertFalse(r["success"])
        self.assertEqual(FK.response.get("http_status_code"), 401)
        # the endpoint signature exposes only cursor/limit -- never a user
        import inspect
        params = list(inspect.signature(ac_api.get_action_items).parameters)
        self.assertEqual(params, ["cursor", "limit"])

    def test_feed_query_is_user_and_open_scoped(self):
        src = io.open(os.path.join(APP, "action_center", "feed.py"), encoding="utf-8").read()
        self.assertIn("allocated_to=%s AND status=%s", src)
        self.assertIn('(user, "Open"', src)
        # single shared service: api delegates, no duplicated classification
        api_src = io.open(os.path.join(APP, "action_center", "api.py"), encoding="utf-8").read()
        self.assertIn("ac_feed.build_feed", api_src)
        self.assertNotIn("bucket_for(", api_src)     # no duplicated classification in api


class TestPmCloseHook(unittest.TestCase):
    def setUp(self):
        _install(FK, purge=False)
        FK.db = _FakeDB(); FK.getall_map = {}
        FK.flags = types.SimpleNamespace(in_install=False, in_migrate=False, in_patch=False)

    def _reload_tasks(self):
        _install(FK, purge=False)   # re-assert our stub (sibling test files swap sys.modules)
        for m in list(sys.modules):
            if m in ("ecentric_workspace.pm.api.todo_lifecycle", "ecentric_workspace.pm.permissions"):
                sys.modules.pop(m, None)
        import importlib
        return importlib.import_module("ecentric_workspace.pm.api.todo_lifecycle")

    def test_close_fires_only_on_terminal_transition(self):
        tasks = self._reload_tasks()
        FK.getall_map = {"ToDo": [{"name": "TD1", "reference_type": "Task",
                                   "reference_name": "TASK-9", "status": "Open"}]}

        class Doc(dict):
            def __init__(self, ws, before_ws, name="TASK-9"):
                super().__init__(workflow_state=ws, status="Working", name=name)
                self.name = name
                self._before = None if before_ws is None else {"workflow_state": before_ws, "status": "Working"}
            def get(self, k, d=None): return dict.get(self, k, d)
            def get_doc_before_save(self): return self._before

        # transition INTO Done -> closes the Open ToDo
        FK.db.set_calls = []
        tasks.pm_task_close_todos_on_terminal(Doc("Done", "In Progress"))
        self.assertEqual(FK.db.set_calls, [("ToDo", "TD1", "status", "Cancelled")])

        # already terminal before -> no-op (idempotent)
        FK.db.set_calls = []
        tasks.pm_task_close_todos_on_terminal(Doc("Done", "Done"))
        self.assertEqual(FK.db.set_calls, [])

        # non-terminal save -> no-op
        FK.db.set_calls = []
        tasks.pm_task_close_todos_on_terminal(Doc("In Progress", "To Do"))
        self.assertEqual(FK.db.set_calls, [])

    def test_hook_wired_and_patch_registered(self):
        hooks = io.open(os.path.join(APP, "hooks.py"), encoding="utf-8").read()
        self.assertIn('"on_update": "ecentric_workspace.pm.api.todo_lifecycle.pm_task_close_todos_on_terminal"', hooks)
        patches = io.open(os.path.join(APP, "patches.txt"), encoding="utf-8").read()
        self.assertIn("action_center.patches.p002_reconcile_stale_task_todos", patches)


class TestReminderSummary(unittest.TestCase):
    def setUp(self):
        _install(FK, purge=False)
        FK.db = _FakeDB(); FK.getall_map = {}; FK.session.user = "u@e.c"
        FK.db.get_value_map = {("Weekly Team Update", "W1", "week_label"): "2026-W30"}

    def test_delegates_feed_and_derives_attention(self):
        FK.db.todo_rows = [
            _todo("a", "", "", date="2026-07-20", created="1"),   # overdue
            _todo("b", "", "", date="2026-07-24", created="2"),   # today -> act_now
            _todo("c", "", "", date="2026-07-30", created="3"),   # upcoming
            _todo("d", "", "", date="", created="4"),             # undated
        ]
        r = ac_api.get_reminder_summary()
        self.assertTrue(r["success"])
        # attention = overdue + act_now
        self.assertEqual(r["attention_count"], r["counts"]["overdue"] + r["counts"]["act_now"])
        self.assertEqual(r["attention_count"], 2)
        self.assertEqual(r["total"], 4)                # ALL open, not just attention
        # same shape/source as build_feed (no duplicated logic)
        self.assertIn("counts", r); self.assertIn("items", r)

    def test_zero_and_guest(self):
        FK.db.todo_rows = []
        r = ac_api.get_reminder_summary()
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["attention_count"], 0)
        FK.session.user = "Guest"
        g = ac_api.get_reminder_summary()
        self.assertFalse(g["success"])
        self.assertEqual(FK.response.get("http_status_code"), 401)

    def test_no_user_param_only_limit(self):
        import inspect
        self.assertEqual(list(inspect.signature(ac_api.get_reminder_summary).parameters), ["limit"])
        src = io.open(os.path.join(APP, "action_center", "api.py"), encoding="utf-8").read()
        self.assertIn("ac_feed.build_feed(user", src)           # delegates
        # no duplicated classification in the api layer
        self.assertNotIn("classify(", src)
        self.assertNotIn('counts["overdue"] += ', src)


if __name__ == "__main__":
    unittest.main()

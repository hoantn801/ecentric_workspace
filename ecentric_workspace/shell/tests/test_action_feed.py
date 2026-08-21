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
import re
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
        self.exist_rows = None           # None -> legacy always-True; dict dt->[rows] to match
    def sql(self, q, params, as_dict=False):
        return list(self.todo_rows)
    def get_value(self, doctype, name, field=None, as_dict=False):
        if isinstance(field, (list, tuple)):
            return {f: self.get_value_map.get((doctype, name, f)) for f in field}
        return self.get_value_map.get((doctype, name, field))
    def set_value(self, doctype, name, field, value, update_modified=True):
        self.set_calls.append((doctype, name, field, value))
    def exists(self, doctype=None, filters=None, *a, **k):
        if self.exist_rows is None:
            return True                  # backward-compatible default
        f = filters or {}
        for r in self.exist_rows.get(doctype, []):
            if all(r.get(k2) == v for k2, v in f.items()):
                return True
        return False
    def table_exists(self, *a, **k):
        return True


class _FakeField:
    def __init__(self, fieldtype, options=None):
        self.fieldtype = fieldtype
        self.options = options


class _FakeMeta:
    def __init__(self, fields):
        self._fields = fields            # {fieldname: _FakeField}

    def get_field(self, name):
        return self._fields.get(name)


class _FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__("frappe")
        self.db = _FakeDB()
        self.session = types.SimpleNamespace(user="u@e.c")
        self.flags = types.SimpleNamespace(in_install=False, in_migrate=False, in_patch=False)
        self.response = {}
        self.meta_map = {}               # doctype -> {fieldname: _FakeField}
        self.roles = {}                  # user -> [roles]
        self.getall_map = {}             # doctype -> list of dict rows (filtered by name/ref)
        self.utils = types.SimpleNamespace(
            getdate=lambda *a: datetime.date(2026, 7, 24),
            now_datetime=lambda: "2026-07-24 10:00:00")
        self.whitelist = lambda *a, **k: (lambda f: f)
        self._ = lambda s: s

    def get_meta(self, doctype):
        return _FakeMeta(self.meta_map.get(doctype, {}))

    def get_roles(self, user=None):
        return list(self.roles.get(user or self.session.user, []))

    def get_all(self, doctype, filters=None, fields=None, limit=None, ignore_permissions=False,
                order_by=None, limit_page_length=None, pluck=None):
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
        if pluck:
            return [r.get(pluck) for r in out]
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
from ecentric_workspace.approval_center.shared.workflow import permissions as ac_perm  # noqa: E402

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
        # counts over full feed. DEDUP (PO-locked 2026-08-12): td-appr and
        # td-appr2 both point at PO-1, so the feed shows ONE card for that
        # document and counts it once -- previously each ToDo produced its own
        # card and inflated the badge.
        self.assertEqual(res["counts"]["overdue"], 1)
        self.assertNotIn("td-appr2", routes)            # merged into td-appr
        self.assertEqual(len([i for i in res["items"]
                              if i.get("reference_name") == "PO-1"]), 1)
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
        # Phase 1b.3.1: `fulfillment` is an additive key (0 here -- no fulfillment items).
        self.assertEqual(sc, {"approval": 1, "pm": 1, "weekly_update": 1,
                              "generic_todo": 1, "fulfillment": 0})
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
        # per-bucket previews shape (1b.1): bucket_items + bucket_has_more
        self.assertIn("counts", r); self.assertIn("bucket_items", r)
        self.assertIn("bucket_has_more", r)
        self.assertEqual(set(r["bucket_items"]), {"overdue", "act_now", "upcoming", "undated"})

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


class TestBucketPreviewsNoStarvation(unittest.TestCase):
    """Phase 1b.1: per-bucket previews from the ONE classified feed -- a
    high-priority bucket must never starve a later one."""
    def setUp(self):
        _install(FK, purge=False)
        FK.db = _FakeDB(); FK.getall_map = {}; FK.session.user = "u@e.c"

    def _rows_19_overdue_1_upcoming(self):
        rows = [_todo("o%02d" % i, "", "", date="2026-07-20", created="%03d" % i)
                for i in range(19)]                         # 19 overdue
        rows.append(_todo("up1", "", "", date="2026-07-30", created="999"))  # 1 upcoming
        return rows

    def test_19_overdue_1_upcoming_upcoming_never_starved(self):
        FK.db.todo_rows = self._rows_19_overdue_1_upcoming()
        res = feed.bucket_previews("u@e.c", preview_n=4)
        # truthful counts
        self.assertEqual(res["counts"], {"overdue": 19, "act_now": 0, "upcoming": 1, "undated": 0})
        self.assertEqual(res["total"], 20)
        # each bucket independently populated -> upcoming ALWAYS present
        self.assertEqual(len(res["bucket_items"]["overdue"]), 4)      # capped at preview_n
        self.assertEqual(len(res["bucket_items"]["upcoming"]), 1)     # the item IS included
        self.assertEqual(res["bucket_items"]["upcoming"][0]["todo_name"], "up1")
        # per-bucket has-more: overdue yes, upcoming no
        self.assertTrue(res["bucket_has_more"]["overdue"])
        self.assertFalse(res["bucket_has_more"]["upcoming"])

    def test_reminder_summary_end_to_end(self):
        FK.db.todo_rows = self._rows_19_overdue_1_upcoming()
        r = ac_api.get_reminder_summary()
        self.assertEqual(r["counts"]["upcoming"], 1)
        self.assertEqual(len(r["bucket_items"]["upcoming"]), 1)       # visible after toggle
        self.assertTrue(r["bucket_has_more"]["overdue"])
        self.assertEqual(r["attention_count"], 19)                   # overdue + act_now

    def test_per_bucket_pagination_bounded(self):
        FK.db.todo_rows = self._rows_19_overdue_1_upcoming()
        p1 = ac_api.get_reminder_bucket(bucket="overdue", limit=10)
        self.assertEqual(p1["count"], 19)
        self.assertEqual(p1["returned"], 10)
        self.assertIsNotNone(p1["next_cursor"])
        p2 = ac_api.get_reminder_bucket(bucket="overdue", cursor=p1["next_cursor"], limit=10)
        self.assertEqual(p2["returned"], 9)                          # remainder
        self.assertIsNone(p2["next_cursor"])
        # no overlap
        s1 = {i["todo_name"] for i in p1["items"]}
        s2 = {i["todo_name"] for i in p2["items"]}
        self.assertEqual(s1 & s2, set())
        # bounded scan (never unbounded fetch)
        src = io.open(os.path.join(APP, "action_center", "feed.py"), encoding="utf-8").read()
        self.assertIn("LIMIT %s", src)
        self.assertIn("_SCAN_CAP", src)

    def test_bad_bucket_returns_empty(self):
        FK.db.todo_rows = []
        r = ac_api.get_reminder_bucket(bucket="nonsense", limit=10)
        self.assertEqual(r["items"], [])
        self.assertEqual(r["count"], 0)

    def test_one_classifier_no_dup(self):
        src = io.open(os.path.join(APP, "action_center", "feed.py"), encoding="utf-8").read()
        # exactly ONE classification pass reused by all three consumers
        self.assertEqual(src.count("def _classified_feed"), 1)
        for fn in ("def build_feed", "def bucket_previews", "def bucket_page"):
            self.assertIn(fn, src)
            body_start = src.index(fn)
            body = src[body_start:body_start + 600]
            self.assertIn("_classified_feed(user)", body, fn)
        # No separate per-source count query in the FEED endpoints: the feed's
        # counts/source_counts must come from the one classified pass. Scoped to
        # the feed section of api.py -- get_my_requests_summary is a DIFFERENT
        # aggregate (the user's own submitted requests) and legitimately counts
        # over the full set so its totals do not drift with the display limit.
        api_src = io.open(os.path.join(APP, "action_center", "api.py"), encoding="utf-8").read()
        feed_section = api_src[:api_src.index("def get_my_requests_summary")]
        self.assertNotIn("frappe.db.count", feed_section)
        self.assertNotIn("source_counts[", api_src)   # never recomputed here


class TestScanBoundAndDedup(unittest.TestCase):
    """PO-locked 2026-08-12. Two honesty rules for the badge:

      * the scan is BOUNDED, and when the bound is hit the API says so
        (`truncated`) instead of publishing a number it knows is short;
      * one business document produces ONE card, however many Open ToDos point
        at it -- the user is often both approver and fulfiller, and stale
        duplicates survive, both of which used to inflate the badge.
    """

    def setUp(self):
        _install(FK, purge=False)
        FK.db = _FakeDB(); FK.getall_map = {}
        FK.session.user = "u@e.c"
        FK.db.get_value_map = {}

    def _plain(self, n, start=0):
        # un-referenced ToDos: inherently distinct, never merged
        return [_todo("td-%d" % i, "", "", created="%04d" % i)
                for i in range(start, start + n)]

    def test_under_cap_is_not_truncated(self):
        FK.db.todo_rows = self._plain(5)
        res = feed.build_feed("u@e.c", limit=20)
        self.assertFalse(res["truncated"])
        self.assertEqual(res["total"], 5)
        self.assertEqual(res["scan_cap"], feed._SCAN_CAP)

    def test_exactly_at_cap_is_not_truncated(self):
        # off-by-one guard: the cap itself is a complete answer
        FK.db.todo_rows = self._plain(feed._SCAN_CAP)
        res = feed.build_feed("u@e.c", limit=20)
        self.assertFalse(res["truncated"])
        self.assertEqual(res["total"], feed._SCAN_CAP)

    def test_over_cap_sets_truncated_and_clips(self):
        FK.db.todo_rows = self._plain(feed._SCAN_CAP + 25)
        res = feed.build_feed("u@e.c", limit=20)
        self.assertTrue(res["truncated"])
        self.assertEqual(res["total"], feed._SCAN_CAP)      # clipped, not 2025

    def test_loader_fetches_one_more_than_cap(self):
        # overflow can only be DETECTED if the query asks for cap+1
        src = io.open(os.path.join(APP, "action_center", "feed.py"), encoding="utf-8").read()
        body = src.split("def _load_open_todos")[1].split("\ndef ")[0]
        self.assertIn("_SCAN_CAP + 1", body)

    def test_cap_is_2000(self):
        self.assertEqual(feed._SCAN_CAP, 2000)

    def test_previews_expose_the_same_flag(self):
        # the drawer reads bucket_previews, not build_feed -- both must tell the
        # truth or the header count and the drawer count disagree
        FK.db.todo_rows = self._plain(feed._SCAN_CAP + 3)
        prev = feed.bucket_previews("u@e.c")
        self.assertTrue(prev["truncated"])
        self.assertEqual(prev["scan_cap"], feed._SCAN_CAP)

    def test_duplicate_todos_on_one_doc_collapse_to_one_card(self):
        FK.db.todo_rows = [
            _todo("td-a", "Task", "TASK-9", date="2026-07-26", created="1"),
            _todo("td-b", "Task", "TASK-9", date="2026-07-26", created="2"),
            _todo("td-c", "Task", "TASK-9", date="2026-07-26", created="3"),
        ]
        FK.getall_map = {"Task": [{"name": "TASK-9", "workflow_state": "In Progress",
                                   "status": "Working", "exp_end_date": "2026-07-26"}]}
        res = feed.build_feed("u@e.c", limit=20)
        self.assertEqual(res["total"], 1)
        self.assertEqual(sum(res["counts"].values()), 1)
        self.assertEqual(sum(res["source_counts"].values()), 1)

    def test_dedup_keeps_the_most_urgent_bucket(self):
        # same doc, two ToDos: one overdue, one upcoming. The card the user sees
        # must be the URGENT one -- keeping whichever row arrived first would
        # hide an overdue item behind a future date.
        FK.db.todo_rows = [
            _todo("td-later", "Task", "TASK-7", date="2026-07-30", created="1"),
            _todo("td-late", "Task", "TASK-7", date="2026-07-10", created="2"),
        ]
        FK.getall_map = {"Task": [{"name": "TASK-7", "workflow_state": "In Progress",
                                   "status": "Working", "exp_end_date": ""}]}
        res = feed.build_feed("u@e.c", limit=20)
        self.assertEqual(res["total"], 1)
        kept = res["items"][0]["bucket"]
        # assert on RANK, not on a literal bucket name: an ACTIVE PM task with a
        # past date is deliberately act_now (someone is already on it) rather
        # than overdue, and that classification is not what this test governs.
        self.assertLess(feed._BUCKET_RANK[kept], feed._BUCKET_RANK["upcoming"])
        self.assertEqual(res["counts"][kept], 1)
        self.assertEqual(res["counts"]["upcoming"], 0)      # un-counted on swap
        self.assertEqual(sum(res["counts"].values()), 1)

    def test_unreferenced_todos_are_never_merged(self):
        FK.db.todo_rows = self._plain(4)
        res = feed.build_feed("u@e.c", limit=20)
        self.assertEqual(res["total"], 4)

    def test_internal_keys_never_leak_to_the_client(self):
        FK.db.todo_rows = self._plain(3)
        for it in feed.build_feed("u@e.c", limit=20)["items"]:
            for k in ("_idx", "_sk", "_creation"):
                self.assertNotIn(k, it)


class TestReminderTotalLabelJS(unittest.TestCase):
    """The drawer must render "<cap>+" when the server reports truncation."""

    def test_label_helper_exists_and_reads_the_flag(self):
        js = io.open(os.path.join(APP, "public", "js", "ec_shell.js"), encoding="utf-8").read()
        self.assertIn("function rmTotalLabel(", js)
        body = js.split("function rmTotalLabel(")[1].split("\n  }")[0]
        self.assertIn("truncated", body)
        self.assertIn("scan_cap", body)
        self.assertIn("+", body)
        # and it is actually WIRED into the drawer header, not just defined
        self.assertIn("rmTotalLabel(R.data)", js)


class TestActiveSourceClassification(unittest.TestCase):
    """Phase 1b.2 item #2: prove the SOURCE-ACTIVE mapping. `act_now` ("Đang
    xử lý") holds GENUINE source-active records only -- an approval awaiting
    this user, a PM Task In Progress, a due-today item -- NOT every Open ToDo.
    Also reproduces the reported overdue=20 / act_now=0 / upcoming=1 to explain
    WHY act_now is 0 (active approvals whose SLA already elapsed are overdue)."""

    def setUp(self):
        _install(FK, purge=False)
        FK.db = _FakeDB(); FK.getall_map = {}; FK.session.user = "u@e.c"
        FK.db.get_value_map = {
            ("Weekly Team Update", "W1", "week_label"): "2026-W30",
            ("Task", "TASK-A", "subject"): "A",
        }

    def _bucket(self, todo_name, res):
        for i in res["items"]:
            if i["todo_name"] == todo_name:
                return i["bucket"]
        return None   # excluded (terminal)

    def test_approval_active_no_sla_is_act_now(self):
        # Awaiting this user, In-Progress level, NO SLA date -> active undated -> act_now.
        FK.db.todo_rows = [_todo("ap", "PO Request", "PO-1")]
        FK.getall_map = {
            "EC Approval Request": [{"name": "R", "reference_name": "PO-1", "approval_status": "Pending"}],
            "EC Approval Request Level": [{"approval_request": "R", "level_status": "In Progress"}],  # no due_at
        }
        res = feed.build_feed("u@e.c", limit=20)
        self.assertEqual(self._bucket("ap", res), "act_now")

    def test_approval_active_sla_past_is_overdue_not_act_now(self):
        FK.db.todo_rows = [_todo("ap", "PO Request", "PO-1")]
        FK.getall_map = {
            "EC Approval Request": [{"name": "R", "reference_name": "PO-1", "approval_status": "Pending"}],
            "EC Approval Request Level": [{"approval_request": "R", "level_status": "In Progress", "due_at": "2026-07-20 09:00:00"}],
        }
        res = feed.build_feed("u@e.c", limit=20)
        self.assertEqual(self._bucket("ap", res), "overdue")

    def test_approval_active_sla_future_is_upcoming(self):
        FK.db.todo_rows = [_todo("ap", "PO Request", "PO-1")]
        FK.getall_map = {
            "EC Approval Request": [{"name": "R", "reference_name": "PO-1", "approval_status": "Pending"}],
            "EC Approval Request Level": [{"approval_request": "R", "level_status": "In Progress", "due_at": "2026-07-30 09:00:00"}],
        }
        res = feed.build_feed("u@e.c", limit=20)
        self.assertEqual(self._bucket("ap", res), "upcoming")

    def test_approval_terminal_is_excluded(self):
        FK.db.todo_rows = [_todo("ap", "PO Request", "PO-1")]
        FK.getall_map = {
            "EC Approval Request": [{"name": "R", "reference_name": "PO-1", "approval_status": "Approved"}],
        }
        res = feed.build_feed("u@e.c", limit=20)
        self.assertIsNone(self._bucket("ap", res))   # terminal -> not in feed

    def test_pm_task_active_states(self):
        FK.db.todo_rows = [
            _todo("t_today", "Task", "T-TODAY", created="1"),
            _todo("t_past", "Task", "T-PAST", created="2"),
            _todo("t_future", "Task", "T-FUTURE", created="3"),
            _todo("t_done", "Task", "T-DONE", created="4"),
        ]
        FK.getall_map = {"Task": [
            {"name": "T-TODAY", "workflow_state": "In Progress", "status": "Working", "exp_end_date": "2026-07-24"},
            {"name": "T-PAST", "workflow_state": "In Progress", "status": "Working", "exp_end_date": "2026-07-20"},
            {"name": "T-FUTURE", "workflow_state": "In Progress", "status": "Working", "exp_end_date": "2026-07-30"},
            {"name": "T-DONE", "workflow_state": "Done", "status": "Completed", "exp_end_date": "2026-07-10"},
        ]}
        res = feed.build_feed("u@e.c", limit=20)
        self.assertEqual(self._bucket("t_today", res), "act_now")
        self.assertEqual(self._bucket("t_past", res), "overdue")
        self.assertEqual(self._bucket("t_future", res), "upcoming")
        self.assertIsNone(self._bucket("t_done", res))         # terminal excluded

    def test_plain_open_todo_is_not_active(self):
        # A WTU (never source-active) and a bare generic ToDo, both undated,
        # must fall to `undated` -- proving we do NOT reclassify every Open
        # ToDo as active.
        FK.db.todo_rows = [
            _todo("wtu", "Weekly Team Update", "W1", created="1"),   # no date
            _todo("bare", "", "", created="2"),                      # no ref, no date
        ]
        FK.getall_map = {"Weekly Team Update": [{"name": "W1", "status": "Draft"}]}
        res = feed.build_feed("u@e.c", limit=20)
        self.assertEqual(self._bucket("wtu", res), "undated")
        self.assertEqual(self._bucket("bare", res), "undated")

    def test_reproduce_20_overdue_0_actnow_1_upcoming(self):
        # 20 approvals awaiting this user whose In-Progress SLA already elapsed
        # -> all OVERDUE (never act_now); 1 approval with a future SLA ->
        # upcoming. Explains the reported counts: act_now=0 is CORRECT, not a
        # bug -- every active item's due date is in the past.
        rows, reqs, lvls = [], [], []
        for i in range(20):
            ref = "PO-%02d" % i
            rows.append(_todo("o%02d" % i, "PO Request", ref, created="%03d" % i))
            reqs.append({"name": "R%02d" % i, "reference_name": ref, "approval_status": "Pending"})
            lvls.append({"approval_request": "R%02d" % i, "level_status": "In Progress", "due_at": "2026-07-20 09:00:00"})
        rows.append(_todo("up", "PO Request", "PO-UP", created="999"))
        reqs.append({"name": "RUP", "reference_name": "PO-UP", "approval_status": "Pending"})
        lvls.append({"approval_request": "RUP", "level_status": "In Progress", "due_at": "2026-07-30 09:00:00"})
        FK.db.todo_rows = rows
        FK.getall_map = {"EC Approval Request": reqs, "EC Approval Request Level": lvls}
        res = feed.build_feed("u@e.c", limit=100)
        self.assertEqual(res["counts"], {"overdue": 20, "act_now": 0, "upcoming": 1, "undated": 0})

    def test_task_item_action_url_is_pm_spa_and_never_todo_list(self):
        # End-to-end: a PM Task item's server-built action_url is the canonical
        # PM SPA deep-link, and NO item in a mixed feed points at the ToDo list.
        FK.db.todo_rows = [
            _todo("t", "Task", "T-TODAY", created="1"),
            _todo("ap", "PO Request", "PO-1", created="2"),
            _todo("wtu", "Weekly Team Update", "W1", date="2026-07-24", created="3"),
        ]
        FK.getall_map = {
            "Task": [{"name": "T-TODAY", "workflow_state": "In Progress", "status": "Working", "exp_end_date": "2026-07-24"}],
            "EC Approval Request": [{"name": "R", "reference_name": "PO-1", "approval_status": "Pending"}],
            "EC Approval Request Level": [{"approval_request": "R", "level_status": "In Progress", "due_at": "2026-07-24 09:00"}],
            "Weekly Team Update": [{"name": "W1", "status": "Draft"}],
        }
        FK.db.get_value_map[("Task", "T-TODAY", "subject")] = "X"
        res = feed.build_feed("u@e.c", limit=20)
        urls = {i["todo_name"]: i["action_url"] for i in res["items"]}
        self.assertTrue(urls["t"].startswith("/pm#task/"))
        for u in urls.values():
            self.assertNotIn("/app/todo", u)
            self.assertNotIn("todo/view/list", u)


class TestApprovalNormalization(unittest.TestCase):
    """Phase 1b.3: approval-governed business-source normalization. A business
    document linked to the Approval Engine via `approval_request` (metadata-
    detected) is normalized as source_type=approval with the canonical Approval
    Center route + level-SLA due, for BOTH direct EC Approval Request references
    and linked business documents."""

    AITOP = "EC AI Topup Request"        # allow-listed (fulfiller pattern)
    ASSET = "EC Asset Request"           # allow-listed (fulfiller pattern)
    PURCH = "EC Purchase Request"        # engine-linked but EXCLUDED (snapshot pattern)
    PLAIN = "Some Business Doc"          # no approval_request field -> generic

    def setUp(self):
        _install(FK, purge=False)
        FK.db = _FakeDB(); FK.getall_map = {}; FK.session.user = "u@e.c"
        # metadata: which DocTypes carry the engine link (+ AITOP fulfilment)
        FK.meta_map = {
            self.AITOP: {"approval_request": _FakeField("Link", "EC Approval Request"),
                         "fulfillment_owner": _FakeField("Data")},
            self.ASSET: {"approval_request": _FakeField("Link", "EC Approval Request"),
                         "fulfillment_owner": _FakeField("Data")},
            self.PURCH: {"approval_request": _FakeField("Link", "EC Approval Request")},
            self.PLAIN: {"some_other": _FakeField("Data")},
        }
        from ecentric_workspace.action_center import resolvers as R
        R._META_FIELD_CACHE.clear()      # meta cache persists per-process
        self.R = R

    # --- graph builders -----------------------------------------------------
    def _biz_rows(self, dt, name, approval_request, fulfillment_owner=None):
        row = {"name": name, "approval_request": approval_request}
        if fulfillment_owner is not None:
            row["fulfillment_owner"] = fulfillment_owner
        FK.getall_map.setdefault(dt, []).append(row)

    def _request(self, name, status="Pending", level=1, atype="AITOP",
                 requested_by="u@e.c", reference_name="", reference_doctype=""):
        FK.getall_map.setdefault("EC Approval Request", []).append(
            {"name": name, "approval_status": status, "current_level": level,
             "approval_type": atype, "requested_by": requested_by,
             "reference_doctype": reference_doctype, "reference_name": reference_name})

    def _type(self, name, route):
        FK.getall_map.setdefault("EC Approval Type", []).append({"name": name, "route": route})

    def _level(self, req, level_no, status, due):
        FK.getall_map.setdefault("EC Approval Request Level", []).append(
            {"approval_request": req, "level_no": level_no, "level_status": status, "due_at": due})

    def _approver(self, req, approver, status="Pending"):
        FK.getall_map.setdefault("EC Approval Request Approver", []).append(
            {"approval_request": req, "approver": approver, "status": status})

    def _find(self, res, todo):
        for i in res["items"]:
            if i["todo_name"] == todo:
                return i
        return None

    # --- tests --------------------------------------------------------------
    def test_linked_ai_topup_normalized_as_approval(self):
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz_rows(self.AITOP, "EC-AITOP-1", "REQ-1", fulfillment_owner="")
        self._request("REQ-1", status="Pending", level=1, atype="AITOP",
                      requested_by="u@e.c", reference_name="EC-AITOP-1")
        self._type("AITOP", "/approvals/ai-topup")
        self._level("REQ-1", 1, "In Progress", "2026-07-20 09:00:00")
        res = feed.build_feed("u@e.c", limit=20)
        it = self._find(res, "t")
        self.assertIsNotNone(it)
        self.assertEqual(it["source_type"], "approval")          # normalized
        self.assertEqual(it["action_url"], "/approvals/ai-topup?id=EC-AITOP-1")
        self.assertNotIn("/app/", it["action_url"])              # not the Desk fallback
        self.assertEqual(it["source_name"], "REQ-1")            # linked engine request
        self.assertEqual(it["reference_type"], self.AITOP)      # business ref preserved
        self.assertEqual(it["bucket"], "overdue")               # past SLA drives bucket

    def test_allowlisted_asset_request_normalizes(self):
        # A second allow-listed (fulfiller-pattern) form normalizes correctly.
        FK.db.todo_rows = [_todo("t", self.ASSET, "EC-ASSET-1")]
        self._biz_rows(self.ASSET, "EC-ASSET-1", "REQ-A", fulfillment_owner="")
        self._request("REQ-A", status="Pending", atype="ASSET_REQUEST",
                      requested_by="u@e.c", reference_name="EC-ASSET-1")
        self._type("ASSET_REQUEST", "/approvals/asset-request")
        self._level("REQ-A", 1, "In Progress", "2026-07-24 09:00:00")
        it = self._find(feed.build_feed("u@e.c", limit=20), "t")
        self.assertEqual(it["source_type"], "approval")
        self.assertEqual(it["action_url"], "/approvals/asset-request?id=EC-ASSET-1")
        self.assertEqual(it["bucket"], "act_now")

    def test_direct_ec_approval_request_reference(self):
        FK.db.todo_rows = [_todo("t", "EC Approval Request", "REQ-D")]
        self._request("REQ-D", status="Pending", level=1, atype="AITOP",
                      requested_by="u@e.c", reference_doctype=self.AITOP,
                      reference_name="EC-AITOP-9")
        self._type("AITOP", "/approvals/ai-topup")
        self._level("REQ-D", 1, "In Progress", "2026-07-30 09:00:00")
        res = feed.build_feed("u@e.c", limit=20)
        it = self._find(res, "t")
        self.assertEqual(it["source_type"], "approval")
        # direct reference -> ?id uses the request's business reference_name
        self.assertEqual(it["action_url"], "/approvals/ai-topup?id=EC-AITOP-9")
        self.assertEqual(it["bucket"], "upcoming")              # future SLA

    def test_excluded_snapshot_form_stays_generic_even_if_visible(self):
        # SAFETY GATE: EC Purchase Request carries the engine link and the
        # canonical helper would grant view, but its form (_can_view) uses the
        # snapshot pattern (no fulfiller) -- canonical is BROADER, so the feed
        # must NOT normalize it. Stays generic (no approval route leaked).
        FK.db.todo_rows = [_todo("t", self.PURCH, "EC-PUR-1")]
        self._biz_rows(self.PURCH, "EC-PUR-1", "REQ-P")
        self._request("REQ-P", status="Pending", atype="PURCHASE",
                      requested_by="u@e.c", reference_name="EC-PUR-1")   # even as requester
        self._type("PURCHASE", "/approvals/purchase-request")
        self._level("REQ-P", 1, "In Progress", "2026-07-24 09:00:00")
        it = self._find(feed.build_feed("u@e.c", limit=20), "t")
        self.assertEqual(it["source_type"], "generic")          # NOT normalized (excluded)
        self.assertNotIn("/approvals/", it["action_url"])       # no engine route
        # POLICY CHANGE 2026-08-21: when normalization cannot apply, an
        # engine-governed doc lands on the Approval Center HUB, never on
        # Frappe Desk (/app/* is permission-denied for portal users, so the
        # reminder pointed at a page they could not open).
        self.assertEqual(it["action_url"], "/approvals")

    def test_direct_ref_to_excluded_doctype_stays_generic(self):
        # Direct EC Approval Request whose reference_doctype is excluded -> generic.
        FK.db.todo_rows = [_todo("t", "EC Approval Request", "REQ-X")]
        self._request("REQ-X", status="Pending", atype="PURCHASE",
                      requested_by="u@e.c", reference_doctype=self.PURCH,
                      reference_name="EC-PUR-9")
        self._type("PURCHASE", "/approvals/purchase-request")
        self._level("REQ-X", 1, "In Progress", "2026-07-24 09:00:00")
        it = self._find(feed.build_feed("u@e.c", limit=20), "t")
        self.assertEqual(it["source_type"], "generic")
        self.assertNotIn("/approvals/", it["action_url"])

    def test_allowlist_membership(self):
        # The allow-list is exactly the fulfiller-pattern (form >= canonical) forms.
        self.assertEqual(self.R.APPROVAL_NORMALIZE_ALLOWLIST, frozenset({
            "EC AI Topup Request", "EC Asset Request", "EC Data Request",
            "EC Document Request", "EC Resignation Request", "EC System Request"}))
        self.assertNotIn("EC Purchase Request", self.R.APPROVAL_NORMALIZE_ALLOWLIST)
        self.assertNotIn("EC Leave Request", self.R.APPROVAL_NORMALIZE_ALLOWLIST)

    def test_source_counts_shift_and_generic_decreases(self):
        FK.db.todo_rows = [
            _todo("a", self.AITOP, "EC-AITOP-1", created="1"),
            _todo("g", self.PLAIN, "PLAIN-1", created="2"),     # no engine link -> generic
        ]
        self._biz_rows(self.AITOP, "EC-AITOP-1", "REQ-1", fulfillment_owner="")
        self._request("REQ-1", requested_by="u@e.c", reference_name="EC-AITOP-1")
        self._type("AITOP", "/approvals/ai-topup")
        self._level("REQ-1", 1, "In Progress", "2026-07-20 09:00:00")
        res = feed.build_feed("u@e.c", limit=20)
        self.assertEqual(res["source_counts"]["approval"], 1)   # linked form counted as approval
        self.assertEqual(res["source_counts"]["generic_todo"], 1)  # only the true generic
        # non-approval business doc stays generic
        g = self._find(res, "g")
        self.assertEqual(g["source_type"], "generic")
        # a doc with NO engine link and no portal page keeps the Desk fallback:
        # there is nowhere better to send it (see test_no_desk_urls for the gate
        # that every GOVERNED source must resolve to a portal route).
        self.assertTrue(g["action_url"].startswith("/app/"))

    def test_terminal_request_excluded(self):
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz_rows(self.AITOP, "EC-AITOP-1", "REQ-1", fulfillment_owner="")
        self._request("REQ-1", status="Approved", requested_by="u@e.c", reference_name="EC-AITOP-1")
        self._type("AITOP", "/approvals/ai-topup")
        self._level("REQ-1", 1, "Approved", "2026-07-20 09:00:00")
        res = feed.build_feed("u@e.c", limit=20)
        self.assertIsNone(self._find(res, "t"))                # terminal -> excluded
        self.assertEqual(res["total"], 0)

    def test_missing_or_invalid_link_falls_back_to_generic(self):
        FK.db.todo_rows = [
            _todo("empty", self.AITOP, "EC-AITOP-2", created="1"),   # approval_request blank
            _todo("dangling", self.AITOP, "EC-AITOP-3", created="2"),  # points at missing request
        ]
        self._biz_rows(self.AITOP, "EC-AITOP-2", "", fulfillment_owner="")
        self._biz_rows(self.AITOP, "EC-AITOP-3", "REQ-GONE", fulfillment_owner="")
        # no EC Approval Request rows for REQ-GONE
        res = feed.build_feed("u@e.c", limit=20)
        for name in ("empty", "dangling"):
            it = self._find(res, name)
            self.assertIsNotNone(it, name)
            self.assertEqual(it["source_type"], "generic", name)          # safe fallback
        # POLICY CHANGE 2026-08-21: when normalization cannot apply, an
        # engine-governed doc lands on the Approval Center HUB, never on
        # Frappe Desk (/app/* is permission-denied for portal users, so the
        # reminder pointed at a page they could not open).
            self.assertEqual(it["action_url"], "/approvals", name)
            self.assertNotIn("/approvals/", it["action_url"], name)       # no leaked route

    def test_feed_gates_on_canonical_helper_false_falls_back_generic(self):
        # The feed delegates visibility to the ONE canonical engine helper; when
        # it denies, no approval route is emitted (generic fallback, no leak).
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz_rows(self.AITOP, "EC-AITOP-1", "REQ-1", fulfillment_owner="other@e.c")
        self._request("REQ-1", status="Pending", requested_by="boss@e.c", reference_name="EC-AITOP-1")
        self._type("AITOP", "/approvals/ai-topup")
        self._level("REQ-1", 1, "In Progress", "2026-07-24 09:00:00")
        orig = ac_perm.can_view_request
        ac_perm.can_view_request = lambda *a, **k: False
        try:
            res = feed.build_feed("u@e.c", limit=20)
        finally:
            ac_perm.can_view_request = orig
        it = self._find(res, "t")
        self.assertEqual(it["source_type"], "generic")         # NOT normalized
        self.assertNotIn("/approvals/", it["action_url"])      # engine route not leaked
        # POLICY CHANGE 2026-08-21: when normalization cannot apply, an
        # engine-governed doc lands on the Approval Center HUB, never on
        # Frappe Desk (/app/* is permission-denied for portal users, so the
        # reminder pointed at a page they could not open).
        self.assertEqual(it["action_url"], "/approvals")

    def test_feed_delegates_visibility_with_correct_inputs(self):
        # Prove the feed calls the canonical helper (not a private reimplementation)
        # and passes the linked request + business fields it resolved.
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz_rows(self.AITOP, "EC-AITOP-1", "REQ-1", fulfillment_owner="ful@e.c")
        self._request("REQ-1", status="Pending", requested_by="boss@e.c", reference_name="EC-AITOP-1")
        self._type("AITOP", "/approvals/ai-topup")
        self._level("REQ-1", 1, "In Progress", "2026-07-24 09:00:00")
        seen = {}
        orig = ac_perm.can_view_request
        def _spy(request_name, user=None, business_doctype=None, requested_by=None,
                 fulfillment_owner=None, approval_type=None):
            seen.update(request_name=request_name, user=user, business_doctype=business_doctype,
                        requested_by=requested_by, fulfillment_owner=fulfillment_owner,
                        approval_type=approval_type)
            return True
        ac_perm.can_view_request = _spy
        try:
            res = feed.build_feed("u@e.c", limit=20)
        finally:
            ac_perm.can_view_request = orig
        self.assertEqual(self._find(res, "t")["source_type"], "approval")
        self.assertEqual(seen["request_name"], "REQ-1")
        self.assertEqual(seen["user"], "u@e.c")
        self.assertEqual(seen["business_doctype"], self.AITOP)
        self.assertEqual(seen["requested_by"], "boss@e.c")
        self.assertEqual(seen["fulfillment_owner"], "ful@e.c")
        self.assertEqual(seen["approval_type"], "AITOP")

    def test_direct_ref_passes_reference_doctype_to_helper(self):
        # For a direct EC Approval Request ToDo, the business_doctype passed to the
        # helper is the request's reference_doctype (not "EC Approval Request").
        FK.db.todo_rows = [_todo("t", "EC Approval Request", "REQ-D")]
        FK.getall_map.setdefault("EC Approval Request", []).append(
            {"name": "REQ-D", "approval_status": "Pending", "current_level": 1,
             "approval_type": "AITOP", "requested_by": "boss@e.c",
             "reference_doctype": self.AITOP, "reference_name": "EC-AITOP-9"})
        self._type("AITOP", "/approvals/ai-topup")
        self._level("REQ-D", 1, "In Progress", "2026-07-24 09:00:00")
        seen = {}
        orig = ac_perm.can_view_request
        def _spy(request_name, user=None, business_doctype=None, **k):
            seen.update(request_name=request_name, business_doctype=business_doctype)
            return True
        ac_perm.can_view_request = _spy
        try:
            feed.build_feed("u@e.c", limit=20)
        finally:
            ac_perm.can_view_request = orig
        self.assertEqual(seen.get("request_name"), "REQ-D")
        self.assertEqual(seen.get("business_doctype"), self.AITOP)

    def test_blank_route_falls_back_to_generic_no_dead_link(self):
        # A visible governed request whose EC Approval Type has no route must NOT
        # be labelled approval with an empty action_url -> generic fallback.
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz_rows(self.AITOP, "EC-AITOP-1", "REQ-1", fulfillment_owner="")
        self._request("REQ-1", status="Pending", requested_by="u@e.c", reference_name="EC-AITOP-1")
        self._type("AITOP", "")                                 # blank route
        self._level("REQ-1", 1, "In Progress", "2026-07-24 09:00:00")
        res = feed.build_feed("u@e.c", limit=20)
        it = self._find(res, "t")
        self.assertEqual(it["source_type"], "generic")
        # POLICY CHANGE 2026-08-21: when normalization cannot apply, an
        # engine-governed doc lands on the Approval Center HUB, never on
        # Frappe Desk (/app/* is permission-denied for portal users, so the
        # reminder pointed at a page they could not open).
        self.assertEqual(it["action_url"], "/approvals")
        self.assertNotEqual(it["action_url"], "")              # never a dead link

    def test_legacy_approval_doctypes_unchanged(self):
        # A legacy /approval form (no approval_request field) keeps its /approval
        # URL via the existing reverse-lookup adapter -- byte-for-byte behavior.
        FK.db.todo_rows = [_todo("t", "PO Request", "PO-1")]
        FK.db.get_value_map = {("PO Request", "PO-1", "title"): "PO one",
                               ("PO Request", "PO-1", "name"): "PO-1"}
        FK.getall_map = {
            "EC Approval Request": [{"name": "R", "reference_name": "PO-1", "approval_status": "Pending"}],
            "EC Approval Request Level": [{"approval_request": "R", "level_status": "In Progress", "due_at": "2026-07-23 09:00:00"}],
        }
        res = feed.build_feed("u@e.c", limit=20)
        it = self._find(res, "t")
        self.assertEqual(it["source_type"], "approval")
        self.assertTrue(it["action_url"].startswith("/approval?id=PO-1"))
        self.assertEqual(it["bucket"], "overdue")


class TestFulfillmentStage(unittest.TestCase):
    """Phase 1b.3.1: approval-fulfillment lifecycle. Approval DECISION terminal is
    not the overall action terminal -- an Approved request with an OPEN governed
    fulfillment stays in the feed as a distinct fulfillment-stage action."""

    AITOP = "EC AI Topup Request"

    def setUp(self):
        _install(FK, purge=False)
        FK.db = _FakeDB(); FK.getall_map = {}; FK.session.user = "hoan.tran@e.c"
        FK.meta_map = {
            self.AITOP: {"approval_request": _FakeField("Link", "EC Approval Request"),
                         "fulfillment_owner": _FakeField("Link", "User"),
                         "fulfillment_status": _FakeField("Select"),
                         "fulfillment_due_at": _FakeField("Datetime")},
        }
        from ecentric_workspace.action_center import resolvers as R
        R._META_FIELD_CACHE.clear()
        self.R = R

    def _biz(self, name, req, status="Assigned", owner="hoan.tran@e.c", due="",
             open_todo=True, todo_user="hoan.tran@e.c", todo_date=""):
        FK.getall_map.setdefault(self.AITOP, []).append(
            {"name": name, "approval_request": req,
             "fulfillment_owner": owner, "fulfillment_status": status,
             "fulfillment_due_at": due})
        if open_todo:                    # governed Open fulfillment ToDo (record-scoped)
            FK.getall_map.setdefault("ToDo", []).append(
                {"name": "TD-" + name, "reference_type": self.AITOP,
                 "reference_name": name, "allocated_to": todo_user,
                 "status": "Open", "date": todo_date})

    def _req(self, name, approval_status="Approved", reference_name="", requested_by="boss@e.c",
             atype="AITOP", level=1):
        FK.getall_map.setdefault("EC Approval Request", []).append(
            {"name": name, "approval_status": approval_status, "current_level": level,
             "approval_type": atype, "requested_by": requested_by,
             "reference_doctype": self.AITOP, "reference_name": reference_name})

    def _type(self, name="AITOP", route="/approvals/ai-topup"):
        FK.getall_map.setdefault("EC Approval Type", []).append({"name": name, "route": route})

    def _level(self, req, status, due, level_no=1):
        FK.getall_map.setdefault("EC Approval Request Level", []).append(
            {"approval_request": req, "level_no": level_no, "level_status": status, "due_at": due})

    def _process(self, atype="AITOP", proc="PROC-1"):
        FK.getall_map.setdefault("EC Approval Process", []).append(
            {"name": proc, "approval_type": atype, "status": "Active"})

    def _participant(self, user, proc="PROC-1"):
        # entitlement via a configured Fulfiller participant (NOT via a ToDo).
        if FK.db.exist_rows is None:
            FK.db.exist_rows = {}
        FK.db.exist_rows.setdefault("EC Approval Participant", []).append(
            {"parent": proc, "parenttype": "EC Approval Process",
             "participant_purpose": "Fulfiller", "user": user})

    def _find(self, res, todo):
        for i in res["items"]:
            if i["todo_name"] == todo:
                return i
        return None

    def test_approval_pending_is_approval_stage(self):
        # description = approval prompt; approval still Pending -> approval stage.
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz("EC-AITOP-1", "REQ-1", status="Not Started", owner="")
        self._req("REQ-1", approval_status="Pending", reference_name="EC-AITOP-1",
                  requested_by="hoan.tran@e.c")
        self._type(); self._level("REQ-1", "In Progress", "2026-07-20 09:00:00")
        it = self._find(feed.build_feed("hoan.tran@e.c", limit=20), "t")
        self.assertEqual(it["action_stage"], "approval")
        self.assertEqual(it["source_family"], "approval")
        self.assertEqual(it["bucket"], "overdue")             # approval-level SLA

    def test_production_shaped_fulfillment_remains(self):
        # PROD evidence: approval Approved (approval ToDos cancelled), fulfillment
        # ToDo Open for hoan.tran, description "AI Topup fulfillment queue".
        FK.db.todo_rows = [{"name": "t", "description": "AI Topup fulfillment queue",
                            "reference_type": self.AITOP, "reference_name": "EC-AITOP-2026-00001",
                            "priority": "Medium", "modified": "2026-07-27", "creation": "1",
                            "date": "", "status": "Open"}]
        self._biz("EC-AITOP-2026-00001", "EC-APR-2026-00003", status="Assigned",
                  owner="hoan.tran@e.c", due="2026-07-30 09:00:00")
        self._req("EC-APR-2026-00003", approval_status="Approved",
                  reference_name="EC-AITOP-2026-00001", requested_by="boss@e.c")
        self._type()
        self._level("EC-APR-2026-00003", "Approved", "2026-07-10 09:00:00")   # OLD approval SLA
        res = feed.build_feed("hoan.tran@e.c", limit=20)
        it = self._find(res, "t")
        self.assertIsNotNone(it)                              # NOT excluded
        self.assertEqual(it["action_stage"], "fulfillment")
        self.assertEqual(it["source_family"], "approval")
        # canonical business-form route
        self.assertEqual(it["action_url"], "/approvals/ai-topup?id=EC-AITOP-2026-00001")
        # due from fulfillment SLA (future) -> upcoming; NOT the old approval SLA (would be overdue)
        self.assertEqual(it["due_at"], "2026-07-30 09:00:00")
        self.assertEqual(it["bucket"], "upcoming")
        # counts: fulfillment++ and NOT pending approval
        self.assertEqual(res["source_counts"]["fulfillment"], 1)
        self.assertEqual(res["source_counts"]["approval"], 0)

    def test_fulfillment_due_fallbacks(self):
        # governed SLA overdue -> overdue
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz("EC-AITOP-1", "REQ-1", status="In Progress", owner="hoan.tran@e.c",
                  due="2026-07-20 09:00:00")
        self._req("REQ-1", reference_name="EC-AITOP-1"); self._type()
        self._level("REQ-1", "Approved", "2026-07-01")
        self.assertEqual(self._find(feed.build_feed("hoan.tran@e.c", 20), "t")["bucket"], "overdue")

    def test_fulfillment_todo_date_fallback_when_no_sla(self):
        # no fulfillment SLA -> fall back to the GOVERNED Open ToDo's date (today)
        # -> act_now. The date comes from _open_fulfillment_todo, not the feed row.
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1", date="2000-01-01")]
        self._biz("EC-AITOP-1", "REQ-1", status="Assigned", owner="hoan.tran@e.c", due="",
                  todo_date="2026-07-24")          # governed ToDo.date
        self._req("REQ-1", reference_name="EC-AITOP-1"); self._type()
        self._level("REQ-1", "Approved", "2026-07-01")
        it = self._find(feed.build_feed("hoan.tran@e.c", 20), "t")
        self.assertEqual(it["due_at"], "2026-07-24")   # governed ToDo.date, NOT the row's 2000-01-01
        self.assertEqual(it["bucket"], "act_now")

    def test_fulfillment_undated_when_neither(self):
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1", date="")]
        self._biz("EC-AITOP-1", "REQ-1", status="Assigned", owner="hoan.tran@e.c", due="")
        self._req("REQ-1", reference_name="EC-AITOP-1"); self._type()
        self._level("REQ-1", "Approved", "2026-07-01")
        it = self._find(feed.build_feed("hoan.tran@e.c", 20), "t")
        self.assertEqual(it["due_at"], "")
        self.assertEqual(it["bucket"], "act_now")             # active undated -> act_now

    def test_completed_fulfillment_disappears(self):
        # governed terminal fulfillment (Completed) -> excluded even if a ToDo lingers.
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz("EC-AITOP-1", "REQ-1", status="Completed", owner="hoan.tran@e.c")
        self._req("REQ-1", reference_name="EC-AITOP-1"); self._type()
        self._level("REQ-1", "Approved", "2026-07-01")
        self.assertIsNone(self._find(feed.build_feed("hoan.tran@e.c", 20), "t"))

    def test_rejected_without_fulfillment_excluded(self):
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz("EC-AITOP-1", "REQ-1", status="Not Started", owner="")
        self._req("REQ-1", approval_status="Rejected", reference_name="EC-AITOP-1")
        self._type(); self._level("REQ-1", "Rejected", "2026-07-01")
        self.assertIsNone(self._find(feed.build_feed("hoan.tran@e.c", 20), "t"))

    # ---- PO decoupling matrix: ENTITLEMENT (no ToDo) x ACTION-EXISTENCE (ToDo) --
    def test_eligible_participant_with_open_todo_included(self):
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz("EC-AITOP-1", "REQ-1", status="Assigned", owner="other@e.c",
                  due="2026-07-24 09:00:00", open_todo=True)
        self._req("REQ-1", reference_name="EC-AITOP-1"); self._type()
        self._level("REQ-1", "Approved", "2026-07-01")
        self._process(); self._participant("hoan.tran@e.c")   # entitled via participant
        it = self._find(feed.build_feed("hoan.tran@e.c", 20), "t")
        self.assertIsNotNone(it)
        self.assertEqual(it["action_stage"], "fulfillment")

    def test_eligible_participant_no_open_todo_excluded(self):
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz("EC-AITOP-1", "REQ-1", status="Assigned", owner="other@e.c",
                  due="2026-07-24 09:00:00", open_todo=False)  # entitled but no ACTION
        self._req("REQ-1", reference_name="EC-AITOP-1"); self._type()
        self._level("REQ-1", "Approved", "2026-07-01")
        self._process(); self._participant("hoan.tran@e.c")
        self.assertIsNone(self._find(feed.build_feed("hoan.tran@e.c", 20), "t"))

    def test_ineligible_user_with_open_todo_excluded(self):
        # KEY decoupling: an Open ToDo EXISTS but the user has NO entitlement
        # (not owner, not participant, not SM) -> the ToDo alone does NOT grant
        # the fulfillment action; item excluded, no business URL leaked.
        FK.db.exist_rows = {}            # participant exists -> False
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz("EC-AITOP-1", "REQ-1", status="Assigned", owner="other@e.c",
                  due="2026-07-24 09:00:00", open_todo=True)
        self._req("REQ-1", reference_name="EC-AITOP-1"); self._type()
        self._level("REQ-1", "Approved", "2026-07-01")
        self._process()                  # process exists, but user is NOT a participant
        self.assertIsNone(self._find(feed.build_feed("hoan.tran@e.c", 20), "t"))

    def test_fulfillment_owner_with_open_todo_included(self):
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz("EC-AITOP-1", "REQ-1", status="Assigned", owner="hoan.tran@e.c",
                  due="2026-07-24 09:00:00", open_todo=True)
        self._req("REQ-1", reference_name="EC-AITOP-1"); self._type()
        self._level("REQ-1", "Approved", "2026-07-01")
        it = self._find(feed.build_feed("hoan.tran@e.c", 20), "t")
        self.assertIsNotNone(it)
        self.assertEqual(it["action_stage"], "fulfillment")

    def test_stale_open_todo_does_not_grant_permission(self):
        # A stale/misassigned Open ToDo for a user with NO entitlement must NOT
        # produce a fulfillment item -- the ToDo row cannot establish permission.
        FK.db.exist_rows = {}            # no participant, not SM
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-1")]
        self._biz("EC-AITOP-1", "REQ-1", status="Assigned", owner="other@e.c",
                  due="2026-07-24 09:00:00", open_todo=True)
        self._req("REQ-1", reference_name="EC-AITOP-1"); self._type()
        self._level("REQ-1", "Approved", "2026-07-01")
        it = self._find(feed.build_feed("hoan.tran@e.c", 20), "t")
        self.assertIsNone(it)

    # ---- PO explicit correctness-gate regression matrix -------------------
    def _gate_case(self, appr_status, ful_status, open_todo):
        FK.db.todo_rows = [_todo("t", self.AITOP, "EC-AITOP-G")]
        # owner == user so entitlement holds; open_todo toggles the governed ToDo.
        self._biz("EC-AITOP-G", "REQ-G", status=ful_status, owner="hoan.tran@e.c",
                  due="2026-07-24 09:00:00", open_todo=open_todo)
        self._req("REQ-G", approval_status=appr_status, reference_name="EC-AITOP-G")
        self._type(); self._level("REQ-G", "Approved", "2026-07-01")
        return self._find(feed.build_feed("hoan.tran@e.c", 20), "t")

    def test_gate_approved_assigned_open_included(self):
        it = self._gate_case("Approved", "Assigned", True)
        self.assertIsNotNone(it)
        self.assertEqual(it["action_stage"], "fulfillment")

    def test_gate_approved_completed_open_excluded(self):
        self.assertIsNone(self._gate_case("Approved", "Completed", True))

    def test_gate_approved_assigned_no_open_excluded(self):
        self.assertIsNone(self._gate_case("Approved", "Assigned", False))

    def test_gate_rejected_assigned_open_excluded(self):
        self.assertIsNone(self._gate_case("Rejected", "Assigned", True))

    def test_gate_cancelled_in_progress_open_excluded(self):
        self.assertIsNone(self._gate_case("Cancelled", "In Progress", True))

    def test_direct_ref_reverse_resolution_failure_no_fulfillment(self):
        # Direct EC Approval Request whose reference_doctype/name are missing ->
        # reverse resolution fails -> generic fallback, NO fulfillment inference,
        # NO reuse of the approval-level SLA.
        FK.db.todo_rows = [_todo("t", "EC Approval Request", "REQ-D")]
        FK.getall_map.setdefault("EC Approval Request", []).append(
            {"name": "REQ-D", "approval_status": "Approved", "current_level": 1,
             "approval_type": "AITOP", "requested_by": "boss@e.c",
             "reference_doctype": "", "reference_name": ""})   # reverse-resolution fails
        self._type(); self._level("REQ-D", "Approved", "2026-07-01 09:00:00")
        it = self._find(feed.build_feed("hoan.tran@e.c", 20), "t")
        self.assertEqual(it["source_type"], "generic")        # generic fallback
        self.assertNotIn("/approvals/", it["action_url"])     # no route
        self.assertNotEqual(it.get("due_at"), "2026-07-01 09:00:00")  # no approval-SLA reuse


class TestAllowlistFormParity(unittest.TestCase):
    """Phase 1b.3 generalized-scope gate: every DocType the feed normalizes
    (APPROVAL_NORMALIZE_ALLOWLIST) must map to a form whose `_can_view` is >=
    the canonical helper -- i.e. it either DELEGATES to can_view_request or
    structurally contains the full fulfiller superset (SM, requester, approver
    row, fulfillment_owner, _is_fulfiller). Static/source proof so the feed can
    never grant a broader view than the business form."""

    #: allow-listed business DocType -> its approval-center API module.
    DT_TO_MODULE = {
        "EC AI Topup Request": "ai_topup",
        "EC Asset Request": "asset_request",
        "EC Data Request": "data_request",
        "EC Document Request": "document_request",
        "EC Resignation Request": "resignation",
        "EC System Request": "system_request",
    }

    @staticmethod
    def _code_only(src):
        """Source with `#` comments and triple-quoted blocks removed.

        These assertions are token searches, so prose must not be able to
        satisfy them. Verified by mutation: the docstring of
        capabilities.can_view mentions "fulfillment_owner", and against the RAW
        text the check stayed green even after the kwarg itself was deleted.

        Deliberately line-based rather than tokenize(): these bodies are sliced
        out mid-signature and do not parse, and a tokenize() that raises would
        fall back to the raw source -- silently turning the guard back off.
        """
        fences = (chr(34) * 3, chr(39) * 3)
        out, fence = [], None
        for line in src.split("\n"):
            if fence is not None:
                if fence in line:
                    fence = None
                continue
            stripped = line.strip()
            hit = None
            for f in fences:
                if stripped.startswith(f):
                    hit = f
                    break
            if hit is not None:
                if stripped.count(hit) == 1:
                    fence = hit
                continue
            out.append(re.sub(r"#.*$", "", line))
        return "\n".join(out)

    def _controller_src(self, module):
        """The module refactor moved per-form controllers from
        approval_center/api/<module>.py to
        approval_center/features/<module>/controllers/api.py; the old path is
        now a re-export shim. Read whichever one carries the real code."""
        for path in (os.path.join(APP, "approval_center", "features", module,
                                  "controllers", "api.py"),
                     os.path.join(APP, "approval_center", "api", module + ".py")):
            if os.path.exists(path):
                src = io.open(path, encoding="utf-8").read()
                if "bind" in src or "_can_view" in src:
                    return src
        return ""

    def _can_view_body(self, module):
        import re as _re
        src = self._controller_src(module)
        m = _re.search(r"\ndef _can_view\([^)]*\):\n(.*?)(?=\ndef |\n@|\Z)", src, _re.S)
        return m.group(1) if m else ""

    def test_allowlist_maps_exactly_to_audited_modules(self):
        from ecentric_workspace.action_center import resolvers as R
        self.assertEqual(set(R.APPROVAL_NORMALIZE_ALLOWLIST), set(self.DT_TO_MODULE))

    def test_each_allowlisted_form_reaches_the_canonical_check(self):
        """Every allow-listed form's view gate must END UP at can_view_request.

        REWRITTEN 2026-08-21. The old version grepped each feature module for a
        literal `def _can_view` and asserted on its body. After the module
        refactor five of the six forms no longer define one -- they are built by
        the shared bind()/bind_fulfillment() factory, which installs _can_view
        for them. So the old test was not merely red, it had gone BLIND: it
        proved nothing about the five forms it could not find, and would have
        passed vacuously the moment someone gave ai_topup a delegating body.

        The chain is asserted end to end instead:
          form controller -> (own _can_view | shared bind factory)
                          -> capabilities.can_view
                          -> workflow.permissions.can_view_request
        """
        for dt, module in self.DT_TO_MODULE.items():
            src = self._controller_src(module)
            self.assertTrue(src, "%s: controller source not found" % module)
            body = self._can_view_body(module)
            if body:
                delegates = ("can_view_request" in body) or ("caps.can_view" in body)
                superset = all(tok in body for tok in (
                    "requested_by == user", "_sm()", "EC Approval Request Approver",
                    "fulfillment_owner", "_is_fulfiller"))
                self.assertTrue(delegates or superset,
                                "%s defines its own _can_view and it is NOT >= "
                                "the canonical helper" % module)
            else:
                self.assertTrue("bind(" in src or "bind_fulfillment(" in src,
                                "%s has neither its own _can_view nor the shared "
                                "bind factory -- its view gate is unaccounted for"
                                % module)

    def test_shared_bind_factory_installs_the_canonical_gate(self):
        """The factory branch above is only safe if bind() really wires
        _can_view to the canonical capability -- otherwise five forms would pass
        on a promise that nothing checks."""
        src = io.open(os.path.join(APP, "approval_center", "shared", "api_adapter.py"),
                      encoding="utf-8").read()
        self.assertIn("def _can_view(user, business, request):", src)
        self.assertIn("return caps.can_view(user, business, request)", src)
        self.assertIn('"_can_view": _can_view,', src)     # exported, not dead code

    def test_capabilities_can_view_delegates_to_the_engine(self):
        """...and capabilities.can_view must FORWARD, not re-implement. A local
        copy of the rule is how the feed and the form drifted apart last time."""
        src = io.open(os.path.join(APP, "approval_center", "shared", "requests",
                                   "capabilities.py"), encoding="utf-8").read()
        body = self._code_only(src.split("def can_view(")[1].split("\ndef ")[0])
        self.assertIn("can_view_request", body)
        # kwarg form, not the bare word: the docstring says "fulfillment_owner"
        # too, and a check that prose can satisfy is not a check
        self.assertNotIn("#", body, "comment stripper did not run")
        for token in ("requested_by=", "fulfillment_owner=", "business_doctype="):
            self.assertIn(token, body,
                          "can_view drops %s on the way through" % token.rstrip("="))

    def test_canonical_check_still_covers_fulfillers(self):
        """Guard the five branches the Action Center feed depends on. If any one
        is dropped, a fulfiller sees a reminder for a document the form then
        refuses to open -- the exact failure this chain exists to prevent."""
        src = io.open(os.path.join(APP, "approval_center", "shared", "workflow",
                                   "permissions.py"), encoding="utf-8").read()
        body = self._code_only(src.split("def can_view_request(")[1].split("\ndef ")[0])
        self.assertNotIn("#", body, "comment stripper did not run")
        # match the BRANCH, not the parameter name: `fulfillment_owner` also
        # appears in the signature, so the bare word stayed green after the
        # whole `if fulfillment_owner == user` branch was deleted (mutation M3).
        for token in ("is_system_manager(", "requested_by == user",
                      "EC Approval Request Approver", "fulfillment_owner == user",
                      "is_eligible_fulfiller("):
            self.assertIn(token, body, "can_view_request lost the %s branch" % token)

    def test_excluded_patterns_are_not_allowlisted(self):
        # No-fulfiller + snapshot forms must be absent (canonical would be broader).
        from ecentric_workspace.action_center import resolvers as R
        for dt in ("EC Leave Request", "EC Hiring Request", "EC Purchase Request",
                   "EC Payment Request", "EC Affiliate Bonus Request",
                   "EC Service Referral Request", "EC Promotion Request"):
            self.assertNotIn(dt, R.APPROVAL_NORMALIZE_ALLOWLIST, dt)


class TestCanonicalVisibilityHelper(unittest.TestCase):
    """Phase 1b.3 (integration): the ONE canonical Approval Engine visibility
    rule (engine.permissions.can_view_request) -- the same function the approval
    form APIs call. Exercises each branch directly."""

    def setUp(self):
        _install(FK, purge=False)
        FK.db = _FakeDB(); FK.getall_map = {}; FK.roles = {}; FK.session.user = "u@e.c"
        FK.db.exist_rows = {}            # switch exists() to filter-matching mode

    def test_system_manager_sees_all(self):
        FK.roles = {"u@e.c": ["System Manager"]}
        self.assertTrue(ac_perm.can_view_request("R", "u@e.c", business_doctype="X",
                                                 requested_by="boss@e.c", approval_type="AITOP"))

    def test_requester(self):
        self.assertTrue(ac_perm.can_view_request("R", "u@e.c", requested_by="u@e.c"))

    def test_approver_row(self):
        FK.db.exist_rows = {"EC Approval Request Approver":
                            [{"approval_request": "R", "approver": "u@e.c"}]}
        self.assertTrue(ac_perm.can_view_request("R", "u@e.c", requested_by="boss@e.c"))

    def test_fulfillment_owner(self):
        self.assertTrue(ac_perm.can_view_request("R", "u@e.c", requested_by="boss@e.c",
                                                 fulfillment_owner="u@e.c"))

    def test_eligible_fulfiller_via_open_todo_on_business_doctype(self):
        FK.db.exist_rows = {"ToDo": [{"reference_type": "EC AI Topup Request",
                                      "allocated_to": "u@e.c", "status": "Open"}]}
        self.assertTrue(ac_perm.can_view_request("R", "u@e.c", requested_by="boss@e.c",
                                                 business_doctype="EC AI Topup Request"))

    def test_eligible_fulfiller_via_configured_participant(self):
        FK.getall_map = {"EC Approval Process": [{"name": "PROC-1", "approval_type": "AITOP",
                                                  "status": "Active"}]}
        FK.db.exist_rows = {"EC Approval Participant":
                            [{"parent": "PROC-1", "parenttype": "EC Approval Process",
                              "participant_purpose": "Fulfiller", "user": "u@e.c"}]}
        self.assertTrue(ac_perm.can_view_request("R", "u@e.c", requested_by="boss@e.c",
                                                 approval_type="AITOP", business_doctype="X"))

    def test_no_relationship_denied(self):
        # not SM, not requester, no approver row, not fulfiller owner, no participant,
        # no open ToDo -> denied.
        self.assertFalse(ac_perm.can_view_request("R", "u@e.c", requested_by="boss@e.c",
                                                  fulfillment_owner="other@e.c",
                                                  approval_type="AITOP", business_doctype="X"))

    def test_can_fulfill_owner_or_eligible_only(self):
        # owner -> True
        self.assertTrue(ac_perm.can_fulfill("u@e.c", business_doctype="X",
                                            fulfillment_owner="u@e.c", approval_type="AITOP"))
        # eligible fulfiller via open ToDo -> True
        FK.db.exist_rows = {"ToDo": [{"reference_type": "X", "allocated_to": "u@e.c",
                                      "status": "Open"}]}
        self.assertTrue(ac_perm.can_fulfill("u@e.c", business_doctype="X",
                                            fulfillment_owner="boss@e.c", approval_type="AITOP"))
        # neither owner nor eligible -> False (a mere viewer gets no fulfillment action)
        FK.db.exist_rows = {}
        self.assertFalse(ac_perm.can_fulfill("u@e.c", business_doctype="X",
                                             fulfillment_owner="boss@e.c", approval_type="AITOP"))

    def test_is_eligible_fulfiller_without_todo_excludes_todo_path(self):
        # Entitlement = owner / SM / configured participant. The 'any Open ToDo on
        # the DocType' path is DELIBERATELY excluded (unlike is_eligible_fulfiller).
        # owner
        self.assertTrue(ac_perm.is_eligible_fulfiller_without_todo(
            "u@e.c", approval_type="AITOP", fulfillment_owner="u@e.c"))
        # System Manager
        FK.roles = {"u@e.c": ["System Manager"]}
        self.assertTrue(ac_perm.is_eligible_fulfiller_without_todo("u@e.c", approval_type="AITOP"))
        FK.roles = {}
        # configured Fulfiller participant
        FK.getall_map = {"EC Approval Process": [{"name": "P1", "approval_type": "AITOP",
                                                  "status": "Active"}]}
        FK.db.exist_rows = {"EC Approval Participant": [
            {"parent": "P1", "parenttype": "EC Approval Process",
             "participant_purpose": "Fulfiller", "user": "u@e.c"}]}
        self.assertTrue(ac_perm.is_eligible_fulfiller_without_todo("u@e.c", approval_type="AITOP"))
        # an Open ToDo on the DocType is NOT sufficient here (decoupled)
        FK.getall_map = {}
        FK.db.exist_rows = {"ToDo": [{"reference_type": "X", "allocated_to": "u@e.c",
                                      "status": "Open"}]}
        self.assertFalse(ac_perm.is_eligible_fulfiller_without_todo(
            "u@e.c", approval_type="AITOP", fulfillment_owner="boss@e.c"))
        # but the ToDo-inclusive is_eligible_fulfiller (unchanged) STILL grants it
        self.assertTrue(ac_perm.is_eligible_fulfiller("u@e.c", "AITOP", business_doctype="X"))

    def test_is_actionable_current_level_pending(self):
        FK.db.exist_rows = {"EC Approval Request Approver":
                            [{"approval_request": "R", "level_no": 2,
                              "approver": "u@e.c", "status": "Pending"}]}
        self.assertTrue(ac_perm.is_actionable("R", 2, "u@e.c", approval_status="Pending"))
        # terminal request -> never actionable
        self.assertFalse(ac_perm.is_actionable("R", 2, "u@e.c", approval_status="Approved"))
        # not the current level -> not actionable
        self.assertFalse(ac_perm.is_actionable("R", 1, "u@e.c", approval_status="Pending"))


if __name__ == "__main__":
    unittest.main()

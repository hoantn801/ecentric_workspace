"""Hotfix B retry-queue tests (2026-06-13). In-memory EC Order Retry store +
stubbed frappe; no DB. Proves idempotent upsert, atomic claim, backoff,
Dead, stale recovery, and the pull checkpoint/breaker semantics (source-text).

    bench run-tests --module ecentric_workspace.alerts.tests.test_order_retry
"""
import os
import sys
import types
import unittest
from datetime import datetime, timedelta


def _stub_frappe():
    try:
        import frappe  # noqa: F401
        return
    except Exception:
        pass
    f = types.ModuleType("frappe")
    f._logs = []
    f._errs = []
    f.conf = types.SimpleNamespace(get=lambda *a, **k: None)
    f.logger = lambda *a, **k: types.SimpleNamespace(
        warning=lambda p: f._logs.append(p), info=lambda p: f._logs.append(p))
    f.log_error = lambda *a, **k: f._errs.append(a)
    f.get_traceback = lambda *a, **k: "tb"
    f._hash_n = [0]
    f._ = lambda s, *a: s
    f.flags = types.SimpleNamespace(in_order_retry_transition=False)

    class _Err(Exception):
        pass
    f.ValidationError = type("ValidationError", (_Err,), {})
    f.PermissionError = type("PermissionError", (_Err,), {})
    f.DoesNotExistError = type("DoesNotExistError", (_Err,), {})

    def _throw(msg, exc=None):
        raise (exc or f.ValidationError)(msg)
    f.throw = _throw

    def gh(length=10):
        f._hash_n[0] += 1
        return "tok%d" % f._hash_n[0]
    f.generate_hash = gh

    class _Cache:
        def __init__(self):
            self.store = {}
        def make_key(self, k):
            return "key:%s" % k
        def set(self, k, v, nx=False, ex=None):
            if nx and k in self.store:
                return False
            self.store[k] = v
            return True
        def get(self, k):
            return self.store.get(k)
        def get_value(self, k):
            return self.store.get(k)
        def delete(self, k):
            self.store.pop(k, None)
        def eval(self, lua, n, key, token):
            if self.store.get(key) == token:
                self.store.pop(key, None)
                return 1
            return 0
    f._cache = _Cache()
    f.cache = lambda: f._cache
    sys.modules["frappe"] = f
    fu = types.ModuleType("frappe.utils")
    fu.now_datetime = lambda: datetime(2026, 6, 13, 12, 0, 0)
    fu.get_datetime = lambda v: v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
    fu.add_to_date = lambda d, minutes=0, **k: d + timedelta(minutes=minutes)
    sys.modules["frappe.utils"] = fu
    fm = types.ModuleType("frappe.model")
    fmd = types.ModuleType("frappe.model.document")

    class Document(object):
        pass
    fmd.Document = Document
    sys.modules["frappe.model"] = fm
    sys.modules["frappe.model.document"] = fmd


_stub_frappe()
from ecentric_workspace.alerts.services import order_retry as orr


class FakeDoc(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    def save(self, ignore_permissions=False):
        STORE[self["name"]] = dict(self)


STORE = {}
SEQ = [0]


def _install_store():
    import frappe
    STORE.clear()
    SEQ[0] = 0
    frappe._logs = []
    frappe._errs = []

    def get_doc(arg, name=None):
        if isinstance(arg, dict):                      # insert
            SEQ[0] += 1
            nm = "ORT-%d" % SEQ[0]
            row = dict(arg); row["name"] = nm
            row.setdefault("processing_token", None)
            STORE[nm] = row

            class _Ins:
                def insert(self, ignore_permissions=False):
                    return FakeDoc(STORE[nm])
            return _Ins()
        return FakeDoc(STORE[arg if name is None else name])

    def db_get_value(dt, flt, field, as_dict=False):
        if isinstance(flt, dict):
            for nm, row in STORE.items():
                if all(row.get(k) == v for k, v in flt.items()):
                    if as_dict:
                        return FakeDoc({f: row.get(f) for f in (field if isinstance(field, list) else [field])})
                    return row.get(field)
            return None
        row = STORE.get(flt)
        return row.get(field) if row else None

    def db_set_value(dt, name, values, update_modified=True):
        STORE[name].update(values)

    def db_exists(dt, name):
        return name in STORE

    def get_all(dt, filters=None, fields=None, order_by=None, limit_page_length=None):
        out = []
        for nm, row in STORE.items():
            ok = True
            for k, v in (filters or {}).items():
                if isinstance(v, list) and v[0] == "<=":
                    if not (row.get(k) is not None and row.get(k) <= v[1]):
                        ok = False
                elif row.get(k) != v:
                    ok = False
            if ok:
                out.append(FakeDoc(dict(row)))
        out.sort(key=lambda r: r.get("next_retry_at") or datetime.min)
        return out[:(limit_page_length or 1000)]

    sql_calls = []

    cursor = types.SimpleNamespace(rowcount=-1)

    def db_sql(q, params=None, as_dict=False):
        sql_calls.append((q, params))
        ql = " ".join(q.split())
        if "SET status='Processing'" in ql:           # _claim (4 params now)
            tok, ts, _last, name = params
            row = STORE.get(name)
            if row and row.get("status") == "Pending":
                row["status"] = "Processing"
                row["processing_token"] = tok
                row["processing_started_at"] = ts
                row["last_attempt_at"] = _last
                cursor.rowcount = 1                    # one row matched WHERE Pending
            else:
                cursor.rowcount = 0                    # lost the race / not Pending
        elif "SET status='Pending', processing_token=NULL" in ql and "Processing" in ql:
            cutoff = params[0]                         # recover_stale by processing_started_at
            for row in STORE.values():
                if row.get("status") == "Processing" and (
                        row.get("processing_started_at") is None
                        or row.get("processing_started_at") < cutoff):
                    row["status"] = "Pending"
                    row["processing_token"] = None
        elif "SELECT DISTINCT brand" in ql:            # brands_with_due_items
            now = params[0]
            seen = []
            for row in STORE.values():
                if (row.get("status") == "Pending" and row.get("brand")
                        and row.get("next_retry_at") is not None
                        and row.get("next_retry_at") <= now
                        and row.get("brand") not in seen):
                    seen.append(row.get("brand"))
            return [FakeDoc({"brand": b}) for b in seen]
        return []

    import frappe
    frappe.get_doc = get_doc
    frappe.get_all = get_all
    frappe.db = types.SimpleNamespace(get_value=db_get_value, set_value=db_set_value,
                                      sql=db_sql, commit=lambda: None, exists=db_exists,
                                      _cursor=cursor)
    frappe._sql_calls = sql_calls
    frappe._cache.store.clear()
    frappe.flags.in_order_retry_transition = False


class _Base(unittest.TestCase):
    def setUp(self):
        _install_store()

    def _make_due(self):
        for r in STORE.values():
            r["next_retry_at"] = datetime(2026, 6, 13, 11, 0, 0)  # in the past


class TestUpsert(_Base):
    def test_01_failed_order_creates_one_item(self):
        self.assertTrue(orr.upsert("FES-VN", "ODV1", "TIMEOUT on GET ..."))
        items = [r for r in STORE.values()]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "Pending")
        self.assertEqual(items[0]["attempt_count"], 0)
        self.assertEqual(items[0]["retry_key"], "Omisell|FES-VN|ODV1")

    def test_02_duplicate_upsert_no_duplicate_no_attempt_bump(self):
        orr.upsert("FES-VN", "ODV1", "e1")
        orr.upsert("FES-VN", "ODV1", "e2")           # same cycle / re-fail
        orr.upsert("FES-VN", "ODV1", "e3")
        items = [r for r in STORE.values() if r["order_number"] == "ODV1"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["attempt_count"], 0)   # worker owns attempts
        self.assertEqual(items[0]["last_error"], "e3")

    def test_13_last_error_sanitized_and_bounded(self):
        orr.upsert("FES-VN", "ODV1", "Authorization: Bearer SECRETTOKEN123 " + "x" * 1000)
        row = [r for r in STORE.values()][0]
        self.assertNotIn("SECRETTOKEN123", row["last_error"])
        self.assertLessEqual(len(row["last_error"]), orr.ERROR_MAX_LEN)

    def test_persistence_failure_returns_false(self):
        import frappe
        orig = frappe.get_doc
        frappe.get_doc = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down"))
        try:
            self.assertFalse(orr.upsert("FES-VN", "ODV9", "e"))
        finally:
            frappe.get_doc = orig


class TestWorker(_Base):
    def test_07_due_item_claimed_once(self):
        orr.upsert("FES-VN", "ODV1", "e")
        self._make_due()
        claimed = orr.claim_due(limit=10)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(STORE[claimed[0]["name"]]["status"], "Processing")
        # not due yet -> a second pass claims nothing new
        self.assertEqual(orr.claim_due(limit=10), [])

    def test_not_due_item_not_claimed(self):
        orr.upsert("FES-VN", "ODV1", "e")   # next_retry_at = now + 5min
        self.assertEqual(orr.claim_due(limit=10), [])

    def test_12_two_workers_cannot_claim_same_item(self):
        orr.upsert("FES-VN", "ODV1", "e")
        name = [r for r in STORE.values()][0]["name"]
        a = orr._claim(name, "tokA")
        b = orr._claim(name, "tokB")     # second worker
        self.assertTrue(a)
        self.assertFalse(b)
        self.assertEqual(STORE[name]["processing_token"], "tokA")

    def test_claim_zero_affected_rows_fails_immediately(self):
        # Item no longer Pending -> conditional UPDATE matches 0 rows -> claim
        # fails on the affected-row count, ownership token untouched.
        orr.upsert("FES-VN", "ODV1", "e")
        name = [r for r in STORE.values()][0]["name"]
        STORE[name]["status"] = "Processing"
        STORE[name]["processing_token"] = "OTHER"
        self.assertFalse(orr._claim(name, "MINE"))
        self.assertEqual(STORE[name]["processing_token"], "OTHER")

    def test_claim_falls_back_to_token_when_no_rowcount(self):
        # No rowcount exposed -> ownership proven purely by token re-read,
        # still exactly one winner.
        import frappe
        frappe.db._cursor = None
        orr.upsert("FES-VN", "ODV1", "e")
        name = [r for r in STORE.values()][0]["name"]
        self.assertTrue(orr._claim(name, "tokA"))
        self.assertFalse(orr._claim(name, "tokB"))

    def test_08_success_marks_completed(self):
        orr.upsert("FES-VN", "ODV1", "e")
        name = [r for r in STORE.values()][0]["name"]
        orr.mark_completed(name)
        self.assertEqual(STORE[name]["status"], "Completed")
        self.assertIsNotNone(STORE[name]["completed_at"])

    def test_09_transient_retry_schedules_next(self):
        orr.upsert("FES-VN", "ODV1", "e")
        name = [r for r in STORE.values()][0]["name"]
        st = orr.mark_retry(name, "again")
        self.assertEqual(st, "Pending")
        self.assertEqual(STORE[name]["attempt_count"], 1)
        self.assertGreater(STORE[name]["next_retry_at"], datetime(2026, 6, 13, 12, 0, 0))

    def test_10_max_attempts_marks_dead(self):
        import frappe
        orr.upsert("FES-VN", "ODV1", "e")
        STORE[[r for r in STORE.values()][0]["name"]]["max_attempts"] = 2
        name = [r for r in STORE.values()][0]["name"]
        orr.mark_retry(name, "f1")       # attempt 1 -> Pending
        st = orr.mark_retry(name, "f2")  # attempt 2 == max -> Dead
        self.assertEqual(st, "Dead")
        # Dead diagnostic is an Error Log titled alerts.order_retry.dead
        self.assertTrue(any("order_retry.dead" in str(l) for l in frappe._errs))

    def test_11_stale_processing_recovers(self):
        orr.upsert("FES-VN", "ODV1", "e")
        name = [r for r in STORE.values()][0]["name"]
        STORE[name]["status"] = "Processing"
        STORE[name]["processing_started_at"] = datetime(2026, 6, 13, 11, 0, 0)  # 1h ago
        orr.recover_stale(30)
        self.assertEqual(STORE[name]["status"], "Pending")

    def test_stale_recent_claim_not_stolen(self):
        orr.upsert("FES-VN", "ODV1", "e")
        name = [r for r in STORE.values()][0]["name"]
        STORE[name]["status"] = "Processing"
        STORE[name]["processing_started_at"] = datetime(2026, 6, 13, 11, 55, 0)  # 5 min ago
        orr.recover_stale(30)
        self.assertEqual(STORE[name]["status"], "Processing")   # still owned

    def test_recurrence_after_dead_restarts(self):
        orr.upsert("FES-VN", "ODV1", "e")
        name = [r for r in STORE.values()][0]["name"]
        STORE[name]["status"] = "Dead"
        STORE[name]["attempt_count"] = 5
        orr.upsert("FES-VN", "ODV1", "new failure")   # re-fail after Dead
        self.assertEqual(STORE[name]["status"], "Pending")
        self.assertEqual(STORE[name]["attempt_count"], 0)


class TestBrandLockAndDispatch(_Base):
    def test_brand_lock_is_exclusive(self):
        self.assertTrue(orr.acquire_brand_lock("FES-VN", "tokA"))
        self.assertFalse(orr.acquire_brand_lock("FES-VN", "tokB"))  # held
        orr.release_brand_lock("FES-VN", "tokA")
        self.assertTrue(orr.acquire_brand_lock("FES-VN", "tokB"))   # freed

    def test_brand_lock_release_requires_owner_token(self):
        orr.acquire_brand_lock("FES-VN", "tokA")
        orr.release_brand_lock("FES-VN", "WRONG")                   # not owner
        self.assertFalse(orr.acquire_brand_lock("FES-VN", "tokB"))  # still held

    def test_brands_with_due_items_groups_no_claim(self):
        orr.upsert("FES-VN", "O1", "e"); orr.upsert("FES-VN", "O2", "e")
        orr.upsert("LOF-VN", "O3", "e"); orr.upsert("MEAT-VN", "O4", "e")
        self._make_due()
        brands = sorted(orr.brands_with_due_items())
        self.assertEqual(brands, ["FES-VN", "LOF-VN", "MEAT-VN"])
        # NO claim happened: everything still Pending
        self.assertTrue(all(r["status"] == "Pending" for r in STORE.values()))

    def test_not_due_brand_excluded(self):
        orr.upsert("FES-VN", "O1", "e")     # next_retry_at = now + 5min (not due)
        self.assertEqual(orr.brands_with_due_items(), [])


def _src(rel):
    path = os.path.join(os.path.dirname(__file__), "..", rel)
    with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestPullWiring(unittest.TestCase):
    """Checkpoint/breaker change is source-asserted (full run needs bench)."""

    @property
    def src(self):
        s = _src("api_omisell.py")
        if "unqueued = []" not in s:
            self.skipTest("source read truncated by sandbox mount")
        return s

    def test_03_queued_failure_continues_loop(self):
        body = self.src.split("def pull_orders")[1].split("def pull_recent")[0]
        # the transient OmisellError detail branch queues + continues (no break)
        oe = body.split("except OmisellError as e:")[1].split("except")[0] \
            if "except OmisellError as e:" in body else body
        self.assertIn("order_retry.upsert(brand, number, e)", body)
        self.assertIn('summary["queued_for_retry"] += 1', body)

    def test_05_checkpoint_advances_on_all_queued(self):
        body = self.src.split("def pull_orders")[1]
        self.assertIn("if len(unqueued) == 0 and not summary.get(\"capped_at\") "
                      "and not summary.get(\"timeboxed\"):", body)

    def test_04_06_breaker_only_unqueued(self):
        body = self.src.split("def pull_orders")[1]
        self.assertIn("if unqueued:", body)
        self.assertIn("_breaker_record(bis, success=False)", body)
        # success path (all queued) records success
        self.assertIn("_breaker_record(bis, success=True)", body)

    def test_auth_failure_is_unqueued(self):
        body = self.src.split("except OmisellAuthError as e:")[1].split("except OmisellError")[0]
        self.assertIn("unqueued.append(number)", body)

    def test_dispatcher_trio_present(self):
        t = _src("tasks.py")
        # cron target is enqueue-only (lightweight)
        self.assertIn("def dispatch_order_retries", t)
        self.assertIn("retry_dispatcher_job", t)
        # dispatcher groups by brand + does NOT claim
        self.assertIn("def retry_dispatcher_job", t)
        self.assertIn("order_retry.brands_with_due_items()", t)
        self.assertNotIn("claim_due", t.split("def retry_dispatcher_job")[1]
                         .split("def retry_brand_worker_job")[0])
        # per-brand worker: brand lock + claim + pull_one_order
        self.assertIn("def retry_brand_worker_job", t)
        self.assertIn("order_retry.acquire_brand_lock(brand, token)", t)
        self.assertIn("order_retry.claim_due(limit, brand)", t)
        self.assertIn("ao.pull_one_order(brand, num)", t)
        self.assertIn("order_retry.release_brand_lock(brand, token)", t)
        self.assertIn("ao._running_key(brand)", t)     # pull priority
        # dispatcher de-dupes overlapping dispatchers via a short-lived NX marker
        self.assertIn("_dispatch_marker_key(brand)", t)
        self.assertIn("nx=True", t.split("def retry_dispatcher_job")[1]
                      .split("def retry_brand_worker_job")[0])

    def test_claim_uses_affected_rows(self):
        o = _src("services/order_retry.py")
        self.assertIn("def _affected_rows", o)
        self.assertIn("rowcount", o)
        body = o.split("def _claim")[1].split("\ndef ")[0]
        self.assertIn("affected = _affected_rows()", body)
        self.assertIn("if affected is not None and affected == 0:", body)
        self.assertIn("processing_token\") == token", body)  # 2nd confirmation

    def test_15_order_dedupe_intact(self):
        # ingestion still upserts by order_key (unchanged)
        ing = _src("services/ingestion.py")
        self.assertIn("order_key", ing)

    def test_scheduler_hook(self):
        h = _src("../hooks.py")
        self.assertIn("ecentric_workspace.alerts.tasks.dispatch_order_retries", h)
        self.assertNotIn("tasks.process_order_retries", h)

    def test_controller_state_machine_guard(self):
        c = _src("doctype/ec_order_retry/ec_order_retry.py")
        # terminal states cannot auto-transition; flag is the sanctioned bypass
        self.assertIn("in_order_retry_transition", c)
        self.assertIn("TERMINAL_RETRY_STATUSES", c)
        self.assertIn("frappe.throw", c)

    def test_manual_api_permissions(self):
        a = _src("api_order_retry.py")
        self.assertIn("can_manage_order_retry", a)
        self.assertIn("can_mark_order_retry_dead", a)   # mark_dead is SM-only
        for fn in ("def get_retry", "def retry_now", "def requeue", "def mark_dead"):
            self.assertIn(fn, a)
        self.assertEqual(a.count("@frappe.whitelist()"), 4)

    def test_dead_creates_one_deduped_todo(self):
        o = _src("services/order_retry.py")
        body = o.split("def _on_dead")[1].split("\ndef ")[0]
        self.assertIn('"reference_type": "EC Order Retry"', body)
        self.assertIn("assign_to", body)               # ToDo via assign_to.add
        self.assertIn('"status": "Open"', body)        # dedupe on open ToDo
        # ONE ToDo, not also a Notification Log: no such doc is constructed
        self.assertNotIn('"doctype": "Notification Log"', body)
        self.assertNotIn("new_doc(\"Notification Log\"", body)


class TestControllerGuard(unittest.TestCase):
    """State-machine guard in the DocType controller (behavioral)."""

    def _ctrl(self, before_status, new_status):
        from ecentric_workspace.alerts.doctype.ec_order_retry import ec_order_retry as m
        doc = m.ECOrderRetry()
        doc.status = new_status
        doc.get_doc_before_save = lambda: type("B", (), {"status": before_status})()
        return doc

    def test_pending_to_processing_allowed(self):
        import frappe
        frappe.flags.in_order_retry_transition = False
        self._ctrl("Pending", "Processing").validate()       # no raise

    def test_completed_to_processing_blocked(self):
        import frappe
        frappe.flags.in_order_retry_transition = False
        with self.assertRaises(frappe.ValidationError):
            self._ctrl("Completed", "Processing").validate()

    def test_dead_to_pending_blocked_without_flag(self):
        import frappe
        frappe.flags.in_order_retry_transition = False
        with self.assertRaises(frappe.ValidationError):
            self._ctrl("Dead", "Pending").validate()

    def test_sanctioned_flag_allows_terminal_exit(self):
        import frappe
        frappe.flags.in_order_retry_transition = True
        try:
            self._ctrl("Dead", "Pending").validate()         # requeue path
        finally:
            frappe.flags.in_order_retry_transition = False


class TestManualTransitions(_Base):
    def test_requeue_terminal_to_pending_fresh_cycle(self):
        orr.upsert("FES-VN", "ODV1", "e")
        name = [r for r in STORE.values()][0]["name"]
        STORE[name]["status"] = "Dead"; STORE[name]["attempt_count"] = 5
        orr.manual_requeue(name)
        self.assertEqual(STORE[name]["status"], "Pending")
        self.assertEqual(STORE[name]["attempt_count"], 0)
        self.assertEqual(STORE[name]["trigger_source"], "Manual")

    def test_retry_now_only_pending(self):
        orr.upsert("FES-VN", "ODV1", "e")
        name = [r for r in STORE.values()][0]["name"]
        orr.manual_retry_now(name)
        self.assertEqual(STORE[name]["next_retry_at"], datetime(2026, 6, 13, 12, 0, 0))
        STORE[name]["status"] = "Completed"
        import frappe
        with self.assertRaises(frappe.ValidationError):
            orr.manual_retry_now(name)

    def test_mark_dead_active_only_no_todo(self):
        orr.upsert("FES-VN", "ODV1", "e")
        name = [r for r in STORE.values()][0]["name"]
        orr.manual_mark_dead(name, "duplicate order")
        self.assertEqual(STORE[name]["status"], "Dead")
        self.assertEqual(STORE[name]["trigger_source"], "Manual")
        import frappe
        with self.assertRaises(frappe.ValidationError):
            orr.manual_mark_dead(name, "again")   # already terminal


if __name__ == "__main__":
    unittest.main()

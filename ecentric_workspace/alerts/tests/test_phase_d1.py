"""Phase D.1 capacity hardening tests.
Pure parts (chunker, constants) run anywhere; the rest needs a bench site:
    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_phase_d1
"""
import json
import unittest
from datetime import datetime

import frappe


class TestChunker(unittest.TestCase):
    def _api(self):
        from ecentric_workspace.alerts import api_omisell
        return api_omisell

    def test_chunks_capped_and_bounded(self):
        api = self._api()
        chunks = api.chunk_windows(datetime(2026, 6, 9, 0, 0), datetime(2026, 6, 9, 10, 0))
        self.assertEqual(len(chunks), api.MAX_CHUNKS_PER_RUN)  # capped at 4
        for f, t in chunks:
            self.assertLessEqual((t - f).total_seconds(), 3600)
        # contiguous, no gaps/overlaps
        for i in range(1, len(chunks)):
            self.assertEqual(chunks[i][0], chunks[i - 1][1])
        self.assertEqual(chunks[0][0], datetime(2026, 6, 9, 0, 0))

    def test_partial_last_chunk(self):
        api = self._api()
        chunks = api.chunk_windows(datetime(2026, 6, 9, 0, 0), datetime(2026, 6, 9, 1, 30))
        self.assertEqual(len(chunks), 2)
        self.assertEqual((chunks[1][1] - chunks[1][0]).total_seconds(), 1800)

    def test_empty_window(self):
        api = self._api()
        self.assertEqual(api.chunk_windows(datetime(2026, 6, 9), datetime(2026, 6, 9)), [])

    def test_d1_constants(self):
        api = self._api()
        self.assertEqual(api.MAX_DETAILS_PER_RUN, 300)
        self.assertEqual(api.MAX_CHUNKS_PER_RUN, 4)
        self.assertEqual(api.CIRCUIT_BREAKER_LIMIT, 3)
        self.assertEqual(api.MAX_WINDOW_SECONDS, 3600)

    def test_read_only_surface_unchanged(self):
        """D.1 must not loosen Phase D guarantees."""
        from ecentric_workspace.alerts.services import omisell_client as oc
        self.assertEqual(oc.ALLOWED_METHODS, frozenset({"GET"}))
        public = [n for n in dir(oc.OmisellClient) if not n.startswith("_")]
        self.assertEqual(sorted(public), ["get_order_detail", "get_orders", "get_shops"])


class TestPullSafety(unittest.TestCase):
    """Hotfix 2026-06-09 (bench 502): pull_recent must enqueue, never do paced
    API work inside a web request; pull_orders must be timeboxed."""

    def _api(self):
        from ecentric_workspace.alerts import api_omisell
        return api_omisell

    def test_budgets_sane(self):
        api = self._api()
        self.assertLessEqual(api.SYNC_TIME_BUDGET, 60)   # < gunicorn timeout
        self.assertGreaterEqual(api.JOB_TIME_BUDGET, 600)
        self.assertGreater(api.JOB_RQ_TIMEOUT, api.JOB_TIME_BUDGET)

    def test_pull_recent_enqueues_not_inline(self):
        import inspect
        api = self._api()
        body = inspect.getsource(api.pull_recent)
        self.assertIn("frappe.enqueue", body)
        self.assertNotIn("pull_orders(", body)  # no inline pulling in web request
        self.assertIn("_running_key", body)     # concurrency lock

    def test_job_exists_and_not_whitelisted(self):
        import inspect
        api = self._api()
        self.assertTrue(callable(api.pull_recent_job))
        src_all = inspect.getsource(api)
        block = src_all.split("def pull_recent_job")[0]
        self.assertFalse(block.rstrip().endswith('@frappe.whitelist(methods=["POST"])')
                         and False)  # structural guard below is the real check
        # the line directly above pull_recent_job must NOT be a whitelist decorator
        lines = src_all.splitlines()
        idx = [i for i, l in enumerate(lines) if l.startswith("def pull_recent_job")][0]
        self.assertNotIn("whitelist", lines[idx - 1])

    def test_pull_orders_has_timebox_param(self):
        import inspect
        api = self._api()
        sig = inspect.signature(api.pull_orders)
        self.assertIn("time_budget", sig.parameters)
        body = inspect.getsource(api.pull_orders)
        self.assertIn("timeboxed", body)
        self.assertIn("time.monotonic", body)

    def test_preview_is_count_only(self):
        import inspect
        api = self._api()
        body = inspect.getsource(api.pull_preview)
        self.assertIn("page_size=1", body)
        self.assertNotIn("get_order_detail", body)
        self.assertNotIn("ingest_orders", body)


class TestObservability(unittest.TestCase):
    """Diag hotfix 2026-06-10: failure context must reach job summary + alert."""

    def _api(self):
        from ecentric_workspace.alerts import api_omisell
        return api_omisell

    def test_job_copies_diagnostic_fields(self):
        import inspect
        body = inspect.getsource(self._api().pull_recent_job)
        for key in ("skipped_status_detail", "failed_order_numbers",
                    "failed_error_summary", "listed_order_numbers", "skipped_manual"):
            self.assertIn('"%s"' % key, body, key)

    def test_format_failure_context(self):
        api = self._api()
        body = api._format_failure_context("2 failures", {
            "window": ["2026-06-07 13:00:00", "2026-06-07 14:00:00"],
            "listed": 5, "ingested": 0, "skipped_status": 3, "failed": 2,
            "failed_order_numbers": ["OMI-1", "OMI-2"],
            "failed_error_summary": {"OMI-1": "HTTP 404 on /api/...", "OMI-2": "Omisell error 400: x"},
            "skipped_status_detail": {"20|Cancelled": 2, "1|Draft": 1},
        })
        for needle in ("2 failures", "13:00:00 -> 2026-06-07 14:00:00",
                       "listed=5", "OMI-1", "HTTP 404", "Cancelled x2"):
            self.assertIn(needle, body, needle)
        self.assertLessEqual(len(body), 1800)
        self.assertNotIn("api_key", body.lower())

    def test_skip_list_parser_safe(self):
        import inspect
        api = self._api()
        body = inspect.getsource(api._skip_orders)
        self.assertIn("ec_alerts_pull_skip_orders", body)
        body2 = inspect.getsource(api.pull_orders)
        self.assertIn("skipped_manual", body2)


class TestDisabledFlagParser(unittest.TestCase):
    """Hotfix 2026-06-09: bool("0") is True - flag needs a real parser."""

    def _parse(self):
        from ecentric_workspace.alerts.api_omisell import parse_disabled_flag
        return parse_disabled_flag

    def test_disabled_values(self):
        p = self._parse()
        for v in (1, "1", True, "true", "TRUE", " yes ", "on", "On", 1.0):
            self.assertTrue(p(v), repr(v))

    def test_not_disabled_values(self):
        p = self._parse()
        for v in (0, "0", False, "false", "FALSE", "no", "off", "", "  ",
                  None, 2, -1, "2", "random", 0.0):
            self.assertFalse(p(v), repr(v))


class TestNoSqlFunctionStrings(unittest.TestCase):
    """Hotfix 2026-06-09 regression guard: newer Frappe rejects SQL function
    strings in SELECT fields (e.g. fields=["count(name) as c"]). Static lint
    over all alerts/ python sources - runs anywhere, no site needed."""

    def test_no_sql_function_strings_in_fields(self):
        import os, re
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pattern = re.compile(r"""fields\s*=\s*\[[^\]]*(count|sum|avg|min|max)\s*\(""", re.I)
        offenders = []
        for root, _dirs, files in os.walk(base):
            if "__pycache__" in root or os.sep + "tests" in root:
                continue
            for fn in files:
                if fn.endswith(".py"):
                    body = open(os.path.join(root, fn), encoding="utf-8").read()
                    if pattern.search(body):
                        offenders.append(fn)
        self.assertEqual(offenders, [])


class TestSchemaD1(unittest.TestCase):
    """Bench-only: indexes + fields landed."""

    def _need_site(self):
        if not getattr(frappe, "db", None) or not hasattr(frappe.db, "sql"):
            self.skipTest("needs bench site")

    def test_search_index_fields(self):
        self._need_site()
        checks = {
            "EC Marketplace Order Log": ["brand", "order_datetime", "sync_status",
                                         "omisell_shop_id", "external_order_id", "platform"],
            "EC Marketplace Order Item": ["seller_sku", "item", "external_line_id"],
            "EC Alert": ["detected_at", "owner_user"],
        }
        for dt, fields in checks.items():
            meta = frappe.get_meta(dt)
            for fn in fields:
                self.assertEqual(int(meta.get_field(fn).search_index or 0), 1, "%s.%s" % (dt, fn))

    def test_composite_indexes_exist(self):
        self._need_site()
        for table, idx in (("tabEC Marketplace Order Log", "brand_order_datetime_index"),
                           ("tabEC Alert", "brand_status_detected_at_index")):
            rows = frappe.db.sql("SHOW INDEX FROM `%s` WHERE Key_name = %%s" % table, idx)
            self.assertTrue(rows, "%s missing %s" % (table, idx))

    def test_bis_consecutive_failures_field(self):
        self._need_site()
        df = frappe.get_meta("EC Brand Integration Settings").get_field("consecutive_failures")
        self.assertIsNotNone(df)
        self.assertEqual(df.fieldtype, "Int")

    def test_list_alerts_total_matches_rows(self):
        self._need_site()
        from ecentric_workspace.alerts import api_alerts
        frappe.set_user("Administrator")
        res = api_alerts.list_alerts(page_len=100)
        raw = len(frappe.get_all("EC Alert", pluck="name", limit_page_length=0))
        self.assertEqual(res["total"], raw)

    def test_get_cards_counts_match_old_method(self):
        self._need_site()
        from ecentric_workspace.alerts import api_alerts
        frappe.set_user("Administrator")
        cards = api_alerts.get_cards()
        raw_open = len(frappe.get_all("EC Alert",
                                      filters={"status": ("in", ["Open", "In Review"])},
                                      pluck="name", limit_page_length=0))
        self.assertEqual(cards["open"], raw_open)

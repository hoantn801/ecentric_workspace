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

    def test_get_cards_counts_match_old_method(self):
        self._need_site()
        from ecentric_workspace.alerts import api_alerts
        frappe.set_user("Administrator")
        cards = api_alerts.get_cards()
        raw_open = len(frappe.get_all("EC Alert",
                                      filters={"status": ("in", ["Open", "In Review"])},
                                      pluck="name", limit_page_length=0))
        self.assertEqual(cards["open"], raw_open)

"""Phase 3 backfill tests (rev Gate 2, 2026-06-13). FIELD-LEVEL idempotency.
In-memory SKU Catalog store + stubbed frappe; no DB.

    bench run-tests --module ecentric_workspace.alerts.tests.test_catalogue_backfill
"""
import json
import sys
import types
import unittest


def _stub_frappe():
    try:
        import frappe  # noqa: F401
        return
    except Exception:
        pass
    f = types.ModuleType("frappe")
    f._errs = []
    f.log_error = lambda *a, **k: f._errs.append(a)
    f.get_traceback = lambda *a, **k: "tb"
    f.logger = lambda *a, **k: types.SimpleNamespace(info=lambda *a, **k: None)
    f.get_all = lambda *a, **k: []
    f.db = types.SimpleNamespace(set_value=lambda *a, **k: None, commit=lambda: None)
    sys.modules["frappe"] = f


_stub_frappe()
from ecentric_workspace.alerts.services import catalogue_backfill as bf

NOTE = json.dumps({
    "src": "catalogue/list", "price_confidence": "low", "sale_price": 222300,
    "catalogue_price": 247000, "image_url": "https://img/x.jpg",
    "catalogue_id": "CAT-1", "status_name": "active", "external_stock": 55,
    "is_variant": 1, "parent_sku": "P-PARENT",
})


class _Base(unittest.TestCase):
    def setUp(self):
        import frappe
        frappe._errs = []
        self.store = {}
        self.writes = []

        def get_all(doctype, filters=None, fields=None, **k):
            mark = '"src": "catalogue/list"'
            return [dict(row, name=name) for name, row in self.store.items()
                    if mark in (row.get("note") or "")]

        def set_value(doctype, name, values, update_modified=True):
            self.writes.append((name, dict(values)))
            self.store[name].update(values)

        frappe.get_all = get_all
        frappe.db.set_value = set_value
        frappe.db.commit = lambda: None

    def _row(self, name, note=NOTE, **over):
        # is_variant defaults to 0 (Check default) -> "populated", preserved.
        r = {"note": note, "last_seen_at": "2026-06-10 00:00:00",
             "image_url": None, "catalogue_price": None, "sale_price": None,
             "external_stock": None, "product_status": None, "catalogue_id": None,
             "parent_sku": None, "is_variant": 0, "price_confidence": None,
             "last_catalogue_sync_at": None}
        r.update(over)
        self.store[name] = r


class TestBackfill(_Base):
    def test_01_newly_backfills_empty_fields(self):
        self._row("S1")
        s = bf.run_backfill()
        row = self.store["S1"]
        self.assertEqual(row["image_url"], "https://img/x.jpg")
        self.assertEqual(row["catalogue_price"], 247000)
        self.assertEqual(row["external_stock"], 55)
        self.assertEqual(row["product_status"], "active")
        self.assertEqual(row["price_confidence"], "low")
        self.assertEqual(row["last_catalogue_sync_at"], "2026-06-10 00:00:00")
        self.assertEqual(s["newly_backfilled"], 1)
        self.assertEqual(s["partially_backfilled"], 0)

    def test_02_rerun_idempotent_fully_already_populated(self):
        self._row("S1")
        bf.run_backfill()
        n = len(self.writes)
        s2 = bf.run_backfill()
        self.assertEqual(s2["newly_backfilled"], 0)
        self.assertEqual(s2["partially_backfilled"], 0)
        self.assertEqual(s2["fully_already_populated"], 1)
        self.assertEqual(len(self.writes), n)            # no further writes

    def test_03_preserve_populated_field(self):
        self._row("S1", image_url="KEEP-ME")
        bf.run_backfill()
        self.assertEqual(self.store["S1"]["image_url"], "KEEP-ME")   # preserved
        self.assertEqual(self.store["S1"]["catalogue_price"], 247000)  # empty -> filled

    def test_04_gate2_marker_set_repairs_only_missing(self):
        # last_catalogue_sync_at already set, but several fields empty -> rerun
        # must populate ONLY the missing ones (partially_backfilled), preserve set.
        self._row("S1", last_catalogue_sync_at="2026-06-12 00:00:00",
                  image_url="HAVE", catalogue_price=None, sale_price=None)
        s = bf.run_backfill()
        row = self.store["S1"]
        self.assertEqual(row["image_url"], "HAVE")           # preserved
        self.assertEqual(row["catalogue_price"], 247000)     # repaired
        self.assertEqual(row["sale_price"], 222300)          # repaired
        self.assertEqual(row["last_catalogue_sync_at"], "2026-06-12 00:00:00")  # marker kept
        self.assertEqual(s["partially_backfilled"], 1)
        self.assertEqual(s["newly_backfilled"], 0)
        # written only the missing fields
        _, vals = self.writes[-1]
        self.assertIn("catalogue_price", vals)
        self.assertNotIn("image_url", vals)
        self.assertNotIn("last_catalogue_sync_at", vals)

    def test_05_malformed_note_skipped_logged(self):
        import frappe
        self._row("S1", note='{"src": "catalogue/list", BROKEN')
        s = bf.run_backfill()
        self.assertEqual(s["malformed"], 1)
        self.assertTrue(frappe._errs)

    def test_06_rsp_price_never_written(self):
        self._row("S1")
        bf.run_backfill()
        for _n, vals in self.writes:
            self.assertNotIn("rsp_price", vals)

    def test_07_note_never_modified(self):
        self._row("S1")
        bf.run_backfill()
        for _n, vals in self.writes:
            self.assertNotIn("note", vals)
        self.assertEqual(self.store["S1"]["note"], NOTE)

    def test_08_is_variant_default_zero_preserved(self):
        # Check default 0 is "populated" -> not overwritten by note is_variant=1
        self._row("S1")
        bf.run_backfill()
        self.assertEqual(self.store["S1"]["is_variant"], 0)

    def test_09_dry_run_no_writes(self):
        self._row("S1")
        s = bf.run_backfill(dry_run=1)
        self.assertEqual(s["newly_backfilled"], 1)
        self.assertEqual(self.writes, [])

    def test_10_summary_keys_deterministic(self):
        self._row("S1")
        self._row("S2", note='{"src": "catalogue/list", BROKEN')
        s = bf.run_backfill()
        for k in ("total_scanned", "eligible", "newly_backfilled",
                  "partially_backfilled", "fully_already_populated",
                  "malformed", "skipped", "failures"):
            self.assertIn(k, s)
        self.assertEqual(s["total_scanned"], 2)
        self.assertEqual(s["malformed"], 1)
        self.assertEqual(s["newly_backfilled"], 1)

    def test_11_non_catalogue_note_not_processed(self):
        self.store["S1"] = {"note": '{"src":"order"}', "image_url": None,
                            "last_catalogue_sync_at": None}
        s = bf.run_backfill()
        self.assertEqual(s["eligible"], 0)
        self.assertIsNone(self.store["S1"]["image_url"])


if __name__ == "__main__":
    unittest.main()

# Copyright (c) 2026, eCentric and contributors
"""Shared action provider v1 contracts (2C.2) -- runnable WITHOUT a bench.

- bucket_for is pure: overdue/today/upcoming and the explicit "undated"
  contract (missing due date is NEVER inferred).
- get_action_items / get_my_requests_summary stay session-scoped: the
  functions accept NO user/filter parameters a client could abuse.
- v0 payload keys are untouched (backward compatibility for any consumer).
"""
import datetime
import io
import inspect
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)

# Stub frappe BEFORE importing the module under test (same pattern as
# test_nav_registry): resolvers/api import frappe at module scope.
if "frappe" not in sys.modules:
    stub = types.ModuleType("frappe")
    stub.whitelist = lambda *a, **k: (lambda f: f)
    stub._ = lambda s: s
    stub.session = types.SimpleNamespace(user="test@example.com")
    stub.utils = types.SimpleNamespace()
    stub.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
    sys.modules["frappe"] = stub

from ecentric_workspace.action_center import resolvers  # noqa: E402

TODAY = datetime.date(2026, 7, 21)


class TestBucketFor(unittest.TestCase):
    def test_overdue_today_upcoming(self):
        self.assertEqual(resolvers.bucket_for("2026-07-20", TODAY), "overdue")
        self.assertEqual(resolvers.bucket_for("2026-07-20 17:00:00", TODAY), "overdue")
        self.assertEqual(resolvers.bucket_for("2026-07-21", TODAY), "today")
        self.assertEqual(resolvers.bucket_for("2026-07-21 09:30:00", TODAY), "today")
        self.assertEqual(resolvers.bucket_for("2026-07-22", TODAY), "upcoming")
        self.assertEqual(resolvers.bucket_for(datetime.date(2026, 8, 1), TODAY), "upcoming")

    def test_missing_or_garbage_due_is_explicitly_undated(self):
        for v in (None, "", "   ", "not-a-date", "2026-13-45", 0):
            self.assertEqual(resolvers.bucket_for(v, TODAY), "undated", repr(v))

    def test_bucket_vocabulary_is_closed(self):
        self.assertEqual(resolvers.BUCKETS, ("overdue", "today", "upcoming", "undated"))


class TestProviderSourceContracts(unittest.TestCase):
    def _src(self, *parts):
        return io.open(os.path.join(APP, *parts), encoding="utf-8").read()

    def test_endpoints_take_no_client_parameters(self):
        # Session-scoped by construction: a client cannot pass user/filters.
        from ecentric_workspace.action_center import api
        self.assertEqual(list(inspect.signature(api.get_action_items).parameters), [])
        self.assertEqual(list(inspect.signature(api.get_my_requests_summary).parameters), [])

    def test_session_user_is_the_only_scope(self):
        src = self._src("action_center", "api.py")
        self.assertIn("allocated_to=%s", src)
        self.assertIn('"requested_by": user', src)
        self.assertIn('frappe.session.user == "Guest"', src)

    def test_v0_payload_keys_unchanged(self):
        src = self._src("action_center", "resolvers.py")
        for key in ('"todo_name"', '"reference_type"', '"reference_name"',
                    '"source_key"', '"source_label"', '"action_label"',
                    '"title"', '"subtitle"', '"action_url"', '"priority"',
                    '"due_at"', '"modified"'):
            self.assertIn(key + ":", src, key)
        # v1 additive keys present
        for key in ('"source_type"', '"source_id"', '"status"',
                    '"resolution_state"', '"bucket"'):
            self.assertIn(key + ":", src, key)

    def test_no_fake_dates_and_no_new_persistence(self):
        api_src = self._src("action_center", "api.py")
        res_src = self._src("action_center", "resolvers.py")
        # due only ever COPIED from ToDo.date or EC Approval Request Level
        self.assertIn("EC Approval Request Level", api_src)
        self.assertNotIn("add_days", api_src)
        self.assertNotIn("frappe.new_doc", api_src)
        self.assertNotIn("insert(", api_src)  # provider is read-only
        self.assertNotIn("insert(", res_src)

    def test_counts_derive_from_the_same_items(self):
        # anti-drift: counts must be accumulated in the same loop that
        # buckets the returned items -- no separate COUNT query.
        api_src = self._src("action_center", "api.py")
        self.assertIn('counts[it["bucket"]]', api_src)
        self.assertNotIn("SELECT COUNT", api_src.upper())


if __name__ == "__main__":
    unittest.main()

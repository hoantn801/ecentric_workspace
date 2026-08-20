# Copyright (c) 2026, eCentric and contributors
"""QC gate: a reminder must never send a portal user to Frappe Desk.

Desk (/app/...) is permission-denied for ordinary portal users, so a reminder
pointing there is a dead end -- the item is visible but unopenable. This has
regressed repeatedly, so the check is automated rather than eyeballed:

  1. SCAN the repo for every DocType this app creates ToDos against.
  2. Assert each one resolves to a PORTAL url through resolve_item.

A new ToDo producer therefore fails this test until its destination is mapped
(a dedicated branch in resolve_item, or PORTAL_FALLBACK).

Run WITHOUT a bench:
  python3 -m unittest ecentric_workspace.action_center.tests.test_no_desk_urls
"""
import os
import re
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))          # .../ecentric_workspace

# minimal frappe stub: resolve_item only needs db.get_value + local + get_meta
_fk = types.ModuleType("frappe")
_fk.__path__ = []
_fk.local = types.SimpleNamespace()
_fk.db = types.SimpleNamespace(get_value=lambda *a, **kw: None)


class _F(dict):
    @property
    def fieldtype(self):
        return self.get("fieldtype")

    @property
    def options(self):
        return self.get("options")


class _Meta:
    """Engine-governed forms declare a Link field `approval_request` pointing at
    EC Approval Request -- the same metadata has_engine_approval_link() reads in
    production. Mirrored here so the gate exercises the REAL code path."""

    def __init__(self, dt):
        self.dt = dt

    def get_field(self, fn):
        if fn == "approval_request" and self.dt.startswith("EC ") and self.dt.endswith(" Request"):
            return _F({"fieldtype": "Link", "options": "EC Approval Request"})
        return None

    def get_title_field(self):
        return "name"

    def has_field(self, fn):
        return self.get_field(fn) is not None


_fk.get_meta = lambda dt: _Meta(dt)
sys.modules.setdefault("frappe", _fk)

from ecentric_workspace.action_center import resolvers as R   # noqa: E402


def _todo(ref_type, ref_name, desc="", name="td-1"):
    return {"name": name, "reference_type": ref_type, "reference_name": ref_name,
            "description": desc, "priority": "Medium", "modified": "", "date": ""}


def _scan_todo_doctypes():
    """DocTypes the app files ToDos against, discovered from source.

    Two shapes are used in this codebase:
      * approval/business modules:  BUSINESS_DT = "EC X Request"
      * alerts:  SETUP_REF_DOCTYPE / reference_type="..." literals
    """
    found = set()
    pat_const = re.compile(r'^(?:BUSINESS_DT|SETUP_REF_DOCTYPE|CASE_REF_DOCTYPE)\s*=\s*"([^"]+)"', re.M)
    pat_ref = re.compile(r'"reference_type"\s*:\s*"([^"]+)"')
    for root, dirs, files in os.walk(APP):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests", "node_modules")]
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            try:
                src = open(p, encoding="utf-8").read()
            except Exception:
                continue
            if "ToDo" not in src and "assign_to" not in src:
                continue
            found.update(pat_const.findall(src))
            found.update(pat_ref.findall(src))
    # not real ToDo targets
    found.discard("ToDo")
    found.discard("Brand Approver")      # retired by alerts p006 (-> "Brand")
    return found


class TestNoDeskUrls(unittest.TestCase):
    def _url(self, ref_type, ref_name="X-1", desc=""):
        return R.resolve_item(_todo(ref_type, ref_name, desc)).get("action_url") or ""

    def test_known_sources_resolve_to_portal(self):
        for dt in ("Weekly Team Update", "Task", "PO Request", "MSO Request",
                   "GBS Sales Order", "Leave Application",
                   "EC Alert", "Brand", "EC Order Retry"):
            url = self._url(dt)
            self.assertTrue(url, dt + ": no url")
            self.assertFalse(url.startswith("/app/"),
                             "%s -> Desk url %s (portal users cannot open it)" % (dt, url))

    def test_no_desk_urls_for_governed_sources(self):
        """THE gate: every ToDo-producing DocType found in the repo must land on
        a portal route. Add a branch in resolve_item or an entry in
        PORTAL_FALLBACK when this fails for a new producer."""
        offenders = []
        for dt in sorted(_scan_todo_doctypes()):
            url = self._url(dt)
            if url.startswith("/app/"):
                offenders.append("%s -> %s" % (dt, url))
        self.assertEqual(offenders, [],
                         "these ToDo sources still point at Frappe Desk:\n  "
                         + "\n  ".join(offenders))

    def test_scan_actually_finds_producers(self):
        # guard against the scanner silently matching nothing (which would make
        # the gate above vacuously pass, exactly how earlier checks went blind)
        found = _scan_todo_doctypes()
        self.assertGreaterEqual(len(found), 5, "scanner found too few producers: %s" % found)
        self.assertIn("Brand", found)

    def test_engine_normalization_wins_over_desk(self):
        # an engine-governed business doc gets the canonical Approval Center URL
        it = R.resolve_item(_todo("EC System Request", "EC-SYSR-1"))
        R.apply_approval_normalization(it, "REQ-1", "/approvals/system-request",
                                       "EC-SYSR-1", stage="fulfillment")
        self.assertEqual(it["action_url"], "/approvals/system-request?id=EC-SYSR-1")
        self.assertFalse(it["action_url"].startswith("/app/"))

    def test_bare_todo_is_the_only_allowed_desk_link(self):
        # a ToDo with no reference has nowhere else to go; documented exception
        url = R.resolve_item(_todo("", "", desc="Ad-hoc", name="td-9")).get("action_url")
        self.assertEqual(url, "/app/todo/td-9")


if __name__ == "__main__":
    unittest.main()

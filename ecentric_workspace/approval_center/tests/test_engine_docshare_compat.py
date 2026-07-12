# Copyright (c) 2026, eCentric and contributors
"""F1 DocShare compatibility shim (engine._engine_grant_read) - commit conditions
2026-07-12:
  * newer Frappe v15 path (add_docshare + flags) works;
  * legacy path (share.add accepting flags) is selected when add_docshare is absent;
  * unrelated exceptions (permission/validation/db) PROPAGATE - never swallowed;
  * recipients / permission flags / assignment behavior are unchanged.

The shim catches ONLY ImportError on the import statement; the share call itself is
never wrapped.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_engine_docshare_compat
"""
from unittest.mock import patch

import frappe
import frappe.share
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import service as engine
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

BIZ = "EC Payment Request"


def _biz_doc():
    requester = fx.user(fx.PFX + "dsc_r@example.com")
    mgr = fx.user(fx.PFX + "dsc_m@example.com")
    fx.employee(requester, reports_to=fx.employee(mgr))
    fx.ensure_process()
    return fx.draft_payment_request(requester), requester, mgr


class TestDocShareCompat(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    # ---------------- current (frappe >= rename) API path ---------------- #
    def test_current_api_path_creates_exact_docshare(self):
        self.assertTrue(hasattr(frappe.share, "add_docshare"),
                        "this runtime is expected to carry the renamed API")
        biz, requester, mgr = _biz_doc()
        user = fx.user(fx.PFX + "dsc_u1@example.com")
        engine._engine_grant_read(BIZ, biz, user)
        row = frappe.db.get_value("DocShare",
                                  {"share_doctype": BIZ, "share_name": biz, "user": user},
                                  ["read", "write", "submit", "share", "everyone"],
                                  as_dict=True)
        # behavior identical to the legacy call: read-only, single user, no everyone
        self.assertEqual((row.read, row.write, row.submit, row.share, row.everyone),
                         (1, 0, 0, 0, 0))
        # exactly ONE recipient - no extra shares created
        self.assertEqual(frappe.db.count("DocShare",
                                         {"share_doctype": BIZ, "share_name": biz}), 1)
        # idempotent: second grant adds nothing
        engine._engine_grant_read(BIZ, biz, user)
        self.assertEqual(frappe.db.count("DocShare",
                                         {"share_doctype": BIZ, "share_name": biz}), 1)

    def test_full_assign_behavior_unchanged(self):
        """End-to-end assignment via the engine helper: ToDo + read DocShare +
        _assign bookkeeping - the recipients and flags the pre-shim code produced."""
        biz, requester, mgr = _biz_doc()
        u = fx.user(fx.PFX + "dsc_u2@example.com")
        engine.assign(BIZ, biz, [u], "compat check")
        self.assertTrue(frappe.db.exists("ToDo", {"reference_type": BIZ,
                                                  "reference_name": biz,
                                                  "allocated_to": u, "status": "Open"}))
        self.assertEqual(frappe.db.get_value(
            "DocShare", {"share_doctype": BIZ, "share_name": biz, "user": u}, "read"), 1)
        assign_list = frappe.parse_json(
            frappe.db.get_value(BIZ, biz, "_assign") or "[]")
        self.assertIn(u, assign_list)

    # ---------------- legacy (pre-rename) API path ---------------- #
    def test_legacy_api_path_selected_and_called_with_flags(self):
        """Simulate an older frappe: add_docshare absent -> the shim must fall back to
        share.add and pass identical arguments including the ignore_share_permission
        flag (recorded via a legacy-signature stub)."""
        biz, requester, mgr = _biz_doc()
        user = fx.user(fx.PFX + "dsc_u3@example.com")
        calls = []

        def legacy_add(doctype, name, u=None, read=1, write=0, submit=0, share=0,
                       everyone=0, flags=None, notify=0):
            calls.append({"doctype": doctype, "name": name, "user": u, "read": read,
                          "write": write, "share": share, "flags": flags})

        real_add_docshare = frappe.share.add_docshare
        try:
            delattr(frappe.share, "add_docshare")  # 'from frappe.share import add_docshare' now ImportErrors
            with patch.object(frappe.share, "add", side_effect=legacy_add):
                engine._engine_grant_read(BIZ, biz, user)
        finally:
            frappe.share.add_docshare = real_add_docshare
        self.assertEqual(len(calls), 1)
        c = calls[0]
        self.assertEqual((c["doctype"], c["name"], c["user"], c["read"], c["write"],
                          c["share"]), (BIZ, biz, user, 1, 0, 0))
        self.assertEqual(c["flags"], {"ignore_share_permission": True})

    # ---------------- unrelated exceptions propagate ---------------- #
    def test_permission_error_from_share_api_propagates(self):
        biz, requester, mgr = _biz_doc()
        user = fx.user(fx.PFX + "dsc_u4@example.com")
        with patch.object(frappe.share, "add_docshare",
                          side_effect=frappe.PermissionError("genuine perm error")):
            with self.assertRaises(frappe.PermissionError):
                engine._engine_grant_read(BIZ, biz, user)

    def test_validation_and_db_errors_propagate(self):
        biz, requester, mgr = _biz_doc()
        user = fx.user(fx.PFX + "dsc_u5@example.com")
        for exc in (frappe.ValidationError("genuine validation"),
                    frappe.db.InternalError("genuine db error")
                    if hasattr(frappe.db, "InternalError") else RuntimeError("db error")):
            with patch.object(frappe.share, "add_docshare", side_effect=exc):
                with self.assertRaises(type(exc)):
                    engine._engine_grant_read(BIZ, biz, user)

    def test_importerror_from_inside_share_api_is_not_masked(self):
        """The shim's except ImportError guards ONLY the import statement. An
        ImportError raised INSIDE the share call must still propagate (it occurs
        after branch selection, outside any try)."""
        biz, requester, mgr = _biz_doc()
        user = fx.user(fx.PFX + "dsc_u6@example.com")
        with patch.object(frappe.share, "add_docshare",
                          side_effect=ImportError("genuine downstream importerror")):
            with self.assertRaises(ImportError):
                engine._engine_grant_read(BIZ, biz, user)

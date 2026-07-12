# Copyright (c) 2026, eCentric and contributors
"""Governed bulk signing (Phase 4). Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_bulk_sign

Bulk = a fail-closed batch over the verified single-item path. Every item is validated
before any enqueue; the whole batch is refused on any failure; each item runs its own
governed worker (exactly one provider write attempt per instance) under one batch key.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import bulk
from ecentric_workspace.approval_center.tests import esign_fixtures as fx
from ecentric_workspace.approval_center.tests import test_uat_pilot as up

DSR = "EC Digital Signature Request"
SETTINGS = "EC Digital Signature Provider Settings"


def _two_ready_same_manager(mgr_tag, r1, r2):
    """Two ready SCTS Payment Requests sharing ONE level-1 approver (the manager)."""
    h1 = up._ready_stack(r1, mgr_tag)          # configures SCTS settings + profile + mapping
    mgr = h1["mgr"]
    # second requester reporting to the SAME manager, then a ready stack reusing that mgr
    h2 = up._ready_stack(r2, mgr_tag)
    name = up._settings_name()
    frappe.db.set_value(SETTINGS, name, "allow_bulk_signing", 1)
    return mgr, h1, h2


def _items(*hs):
    return [{"business_doctype": "EC Payment Request", "business_name": h["biz"]} for h in hs]


class TestBulkSign(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_preview_all_eligible(self):
        mgr, h1, h2 = _two_ready_same_manager("bkm", "bk1r", "bk2r")
        frappe.set_user(mgr)
        out = bulk.preview_bulk(_items(h1, h2))
        frappe.set_user("Administrator")
        self.assertTrue(out["all_eligible"], out)

    def test_two_eligible_requests_one_batch_key(self):
        mgr, h1, h2 = _two_ready_same_manager("bkm2", "bk3r", "bk4r")
        frappe.set_user(mgr)
        out = bulk.bulk_sign(_items(h1, h2))
        frappe.set_user("Administrator")
        self.assertEqual(out["count"], 2)
        keys = set(frappe.db.get_value(DSR, i["signature_request"], "bulk_batch_key")
                   for i in out["items"])
        self.assertEqual(len(keys), 1)               # one shared correlation key
        self.assertEqual(next(iter(keys)), out["batch_key"])

    def test_bulk_gate_off_blocks(self):
        mgr, h1, h2 = _two_ready_same_manager("bkm3", "bk5r", "bk6r")
        frappe.db.set_value(SETTINGS, up._settings_name(), "allow_bulk_signing", 0)
        frappe.set_user(mgr)
        with self.assertRaises(frappe.PermissionError):
            bulk.bulk_sign(_items(h1, h2))
        frappe.set_user("Administrator")

    def test_wrong_caller_blocks_whole_batch(self):
        mgr, h1, h2 = _two_ready_same_manager("bkm4", "bk7r", "bk8r")
        up._grant_sm(fx.CEO)                          # SM but not the active approver
        frappe.set_user(fx.CEO)
        with self.assertRaises(frappe.ValidationError):
            bulk.bulk_sign(_items(h1, h2))
        frappe.set_user("Administrator")

    def test_administrator_no_bypass(self):
        mgr, h1, h2 = _two_ready_same_manager("bkm5", "bk9r", "bk10r")
        frappe.set_user("Administrator")             # SM, not the active approver
        with self.assertRaises(frappe.ValidationError):
            bulk.bulk_sign(_items(h1, h2))

    def test_one_invalid_item_fails_pre_write(self):
        mgr, h1, h2 = _two_ready_same_manager("bkm6", "bk11r", "bk12r")
        # invalidate h2's package hash so it fails readiness
        ar2 = frappe.db.get_value("EC Payment Request", h2["biz"], "approval_request")
        from ecentric_workspace.approval_center.esign import package as pkgsvc
        pkg2 = pkgsvc.active_package_for_request(ar2)
        frappe.db.set_value("EC Digital Signature Package", pkg2, "package_hash", "TAMPERED")
        frappe.set_user(mgr)
        before = frappe.db.count(DSR)
        with self.assertRaises(frappe.ValidationError):
            bulk.bulk_sign(_items(h1, h2))
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.count(DSR), before)   # nothing enqueued (fail before write)

    def test_duplicate_invocation_idempotent(self):
        mgr, h1, h2 = _two_ready_same_manager("bkm7", "bk13r", "bk14r")
        frappe.set_user(mgr)
        first = bulk.bulk_sign(_items(h1, h2))
        second = bulk.bulk_sign(_items(h1, h2))       # per-item idempotency key dedupes
        frappe.set_user("Administrator")
        self.assertTrue(all(i.get("duplicate") for i in second["items"]))

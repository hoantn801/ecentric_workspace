# Copyright (c) 2026, eCentric and contributors
"""Governed multi-select SEQUENTIAL signing (PR#148 rename of the former "bulk"). Runs on the
bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_multi_sign

Not provider bulk: each item is signed independently through the verified single-item path;
fail-closed as a selection; gate OFF by default; no provider batch call is made or implied.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import multi_sign
from ecentric_workspace.approval_center.tests import esign_fixtures as fx
from ecentric_workspace.approval_center.tests import test_uat_pilot as up

DSR = "EC Digital Signature Request"
SETTINGS = "EC Digital Signature Provider Settings"


def _two_ready_same_manager(mgr_tag, r1, r2):
    h1 = up._ready_stack(r1, mgr_tag)
    mgr = h1["mgr"]
    h2 = up._ready_stack(r2, mgr_tag)
    frappe.db.set_value(SETTINGS, up._settings_name(), "allow_bulk_signing", 1)
    return mgr, h1, h2


def _items(*hs):
    return [{"business_doctype": "EC Payment Request", "business_name": h["biz"]} for h in hs]


class TestMultiSelectSequentialSign(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_preview_all_eligible(self):
        mgr, h1, h2 = _two_ready_same_manager("msm", "ms1r", "ms2r")
        frappe.set_user(mgr)
        out = multi_sign.preview_multi_select(_items(h1, h2))
        frappe.set_user("Administrator")
        self.assertTrue(out["all_eligible"], out)
        self.assertEqual(out["mode"], "multi_select_sequential")

    def test_two_items_one_selection_key(self):
        mgr, h1, h2 = _two_ready_same_manager("msm2", "ms3r", "ms4r")
        frappe.set_user(mgr)
        out = multi_sign.multi_select_sequential_sign(_items(h1, h2))
        frappe.set_user("Administrator")
        self.assertEqual(out["count"], 2)
        keys = set(frappe.db.get_value(DSR, i["signature_request"], "bulk_batch_key")
                   for i in out["items"])
        self.assertEqual(len(keys), 1)
        self.assertEqual(next(iter(keys)), out["selection_key"])
        self.assertTrue(out["selection_key"].startswith("MSEQ-"))

    def test_gate_off_blocks(self):
        mgr, h1, h2 = _two_ready_same_manager("msm3", "ms5r", "ms6r")
        frappe.db.set_value(SETTINGS, up._settings_name(), "allow_bulk_signing", 0)
        frappe.set_user(mgr)
        with self.assertRaises(frappe.PermissionError):
            multi_sign.multi_select_sequential_sign(_items(h1, h2))
        frappe.set_user("Administrator")

    def test_wrong_caller_blocks_whole_selection(self):
        mgr, h1, h2 = _two_ready_same_manager("msm4", "ms7r", "ms8r")
        up._grant_sm(fx.CEO)
        frappe.set_user(fx.CEO)
        with self.assertRaises(frappe.ValidationError):
            multi_sign.multi_select_sequential_sign(_items(h1, h2))
        frappe.set_user("Administrator")

    def test_administrator_no_bypass(self):
        mgr, h1, h2 = _two_ready_same_manager("msm5", "ms9r", "ms10r")
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.ValidationError):
            multi_sign.multi_select_sequential_sign(_items(h1, h2))

    def test_one_invalid_item_fails_pre_write(self):
        mgr, h1, h2 = _two_ready_same_manager("msm6", "ms11r", "ms12r")
        ar2 = frappe.db.get_value("EC Payment Request", h2["biz"], "approval_request")
        from ecentric_workspace.approval_center.esign import package as pkgsvc
        pkg2 = pkgsvc.active_package_for_request(ar2)
        frappe.db.set_value("EC Digital Signature Package", pkg2, "package_hash", "TAMPERED")
        frappe.set_user(mgr)
        before = frappe.db.count(DSR)
        with self.assertRaises(frappe.ValidationError):
            multi_sign.multi_select_sequential_sign(_items(h1, h2))
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.count(DSR), before)

    def test_no_provider_batch_event_emitted(self):
        mgr, h1, h2 = _two_ready_same_manager("msm7", "ms13r", "ms14r")
        frappe.set_user(mgr)
        multi_sign.multi_select_sequential_sign(_items(h1, h2))
        frappe.set_user("Administrator")
        # the accurate sequential event is emitted; the reserved provider-batch event is NOT
        self.assertTrue(frappe.db.exists("EC Digital Signature Event",
                                         {"event_type": "MultiSelectSequentialSubmitted"}))
        self.assertFalse(frappe.db.exists("EC Digital Signature Event",
                                          {"event_type": "BulkBatchSubmitted"}))

    def test_duplicate_invocation_idempotent(self):
        mgr, h1, h2 = _two_ready_same_manager("msm8", "ms15r", "ms16r")
        frappe.set_user(mgr)
        multi_sign.multi_select_sequential_sign(_items(h1, h2))
        second = multi_sign.multi_select_sequential_sign(_items(h1, h2))
        frappe.set_user("Administrator")
        self.assertTrue(all(i.get("duplicate") for i in second["items"]))

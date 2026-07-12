# Copyright (c) 2026, eCentric and contributors
"""Verification Gate item G (+ guard-matrix extensions from item B): feature gates,
scheduler kill switch, production block, mock-only adapter, superseded/cancelled DSR
rejection.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_gates
"""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.esign import guard, tasks, service as esvc
from ecentric_workspace.approval_center.esign.providers import get_adapter
from ecentric_workspace.approval_center.esign.providers.base import ProviderError
from ecentric_workspace.approval_center.tests import esign_fixtures as fx


class TestEsignGates(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")
        setattr(frappe.flags, guard.FLAG_KEY, None)

    # ---------------- feature gates ---------------- #
    def _drop_prod_row(self):
        # a committed Mock::Production row may pre-exist on a shared/disposable site
        n = frappe.db.get_value("EC Digital Signature Provider Settings",
                                {"provider": "Mock", "environment": "Production"}, "name")
        if n:
            frappe.delete_doc("EC Digital Signature Provider Settings", n,
                              ignore_permissions=True, force=True)

    def test_all_gates_default_closed_on_fresh_settings_row(self):
        self._drop_prod_row()
        name = frappe.get_doc({"doctype": "EC Digital Signature Provider Settings",
                               "provider": "Mock", "environment": "Production",
                               "base_url": "x"}).insert(ignore_permissions=True).name
        s = frappe.db.get_value("EC Digital Signature Provider Settings", name, "*",
                                as_dict=True)
        for gate in ("integration_enabled", "allow_document_creation", "allow_signing",
                     "allow_bulk_signing", "allow_external_signer", "allow_callback",
                     "allow_production_signing"):
            self.assertFalse(s.get(gate), gate)

    def test_production_signing_blocked_without_master_gate(self):
        self._drop_prod_row()
        # controller: Production row cannot enable signing without allow_production_signing
        doc = frappe.get_doc({"doctype": "EC Digital Signature Provider Settings",
                              "provider": "Mock", "environment": "Production",
                              "base_url": "x", "integration_enabled": 1,
                              "allow_signing": 1})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
        # guard: even if such a row existed (bypassing controller), gates stay closed
        frappe.db.sql("""delete from `tabEC Digital Signature Provider Settings`
                         where provider='Mock' and environment='Production'""")
        frappe.get_doc({"doctype": "EC Digital Signature Provider Settings",
                        "provider": "Mock", "environment": "Production",
                        "base_url": "x"}).insert(ignore_permissions=True)
        frappe.db.set_value("EC Digital Signature Provider Settings",
                            {"provider": "Mock", "environment": "Production"},
                            {"integration_enabled": 1, "allow_signing": 1})
        self.assertFalse(guard._gates_open("Mock", "Production"))

    def test_no_profile_rows_shipped_and_guard_inert(self):
        # S2A ships zero seeded profiles: any pre-existing rows are test artifacts
        # with the ZZESN_ prefix only.
        others = frappe.get_all("EC Digital Signature Profile",
                                filters={"name": ["not like", "ZZESN%"]}, pluck="name")
        self.assertEqual(others, [])
        self.assertFalse(guard.level_requires_signature("EC Data Request",
                                                        "DATA_REQUEST", 1))

    # ---------------- scheduler kill switch ---------------- #
    def test_scheduler_jobs_noop_when_disabled(self):
        with patch.object(tasks, "_disabled", return_value=True):
            with patch.object(frappe, "get_all",
                              side_effect=AssertionError("must not query")) as _:
                self.assertIsNone(tasks.poll_pending())
                self.assertIsNone(tasks.sweep_stale())
                self.assertIsNone(tasks.orphan_file_scan())

    def test_kill_switch_fail_safe_on_broken_config(self):
        with patch.object(frappe, "conf") as conf:
            conf.get.side_effect = RuntimeError("broken site_config")
            self.assertTrue(tasks._disabled())  # error => DISABLED

    # ---------------- adapters ---------------- #
    def test_scts_adapter_not_available_in_s2a(self):
        with self.assertRaises(ProviderError) as ctx:
            get_adapter({"provider": "SCTS"})
        self.assertEqual(ctx.exception.code, "scts_adapter_not_implemented")

    def test_unknown_provider_rejected(self):
        with self.assertRaises(ProviderError):
            get_adapter({"provider": "Evil"})

    # ---------------- B extensions: dead DSR states never authorize ---------------- #
    def test_superseded_and_cancelled_dsr_rejected_as_completion_credential(self):
        h = fx.full_stack(fx.PFX + "gt1r@example.com", fx.PFX + "gt1m@example.com")
        frappe.set_user(h["mgr"])
        res = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        dsr = res["signature_request"]
        req = frappe.get_doc("EC Approval Request", h["ar"])
        for dead in ("Superseded", "Cancelled"):
            frappe.db.set_value("EC Digital Signature Request", dsr,
                                {"status": dead, "verified_at": frappe.utils.now_datetime()})
            with self.assertRaises(frappe.PermissionError):
                guard.validate_completion(dsr, req, req.current_level, h["mgr"])

    def test_wrong_level_dsr_rejected(self):
        h = fx.full_stack(fx.PFX + "gt2r@example.com", fx.PFX + "gt2m@example.com")
        frappe.set_user(h["mgr"])
        res = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        dsr = res["signature_request"]
        frappe.db.set_value("EC Digital Signature Request", dsr,
                            {"status": "Signed", "verified_at": frappe.utils.now_datetime()})
        # point the DSR at level 2's runtime row -> level mismatch must block
        rl2 = frappe.db.get_value("EC Approval Request Level",
                                  {"approval_request": h["ar"], "level_no": 2}, "name")
        frappe.db.set_value("EC Digital Signature Request", dsr, "request_level", rl2)
        req = frappe.get_doc("EC Approval Request", h["ar"])
        with self.assertRaises(frappe.PermissionError):
            guard.validate_completion(dsr, req, req.current_level, h["mgr"])

    def test_wrong_business_document_rejected(self):
        h = fx.full_stack(fx.PFX + "gt3r@example.com", fx.PFX + "gt3m@example.com")
        frappe.set_user(h["mgr"])
        res = esvc.approve_and_sign("EC Payment Request", h["biz"])
        frappe.set_user("Administrator")
        dsr = res["signature_request"]
        frappe.db.set_value("EC Digital Signature Request", dsr,
                            {"status": "Signed", "verified_at": frappe.utils.now_datetime()})
        frappe.db.set_value("EC Digital Signature Package", h["pkg"],
                            "business_name", "EC-PAYR-2099-00001")
        req = frappe.get_doc("EC Approval Request", h["ar"])
        with self.assertRaises(frappe.PermissionError):
            guard.validate_completion(dsr, req, req.current_level, h["mgr"])

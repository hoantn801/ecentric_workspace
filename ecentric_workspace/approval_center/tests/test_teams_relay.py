# Copyright (c) 2026, eCentric and contributors
"""engine.notify -> Teams DM relay: link builder + kill-switch + per-recipient send."""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import service as engine


class TestTeamsRelay(FrappeTestCase):
    def test_kill_switch_blocks_send(self):
        orig = frappe.conf.get("ec_approval_teams_disabled")
        frappe.conf.ec_approval_teams_disabled = 1
        try:
            calls = []
            import ecentric_workspace.notification_center.providers.teams_bot as tb
            real = tb.send_personal
            tb.send_personal = lambda *a, **k: calls.append(a)
            try:
                engine._send_teams_batch(["x@x.com"], "hi", "EC Approval Type", "X")
            finally:
                tb.send_personal = real
            self.assertEqual(calls, [])
        finally:
            frappe.conf.ec_approval_teams_disabled = orig

    def test_send_calls_per_recipient_when_configured(self):
        import ecentric_workspace.notification_center.providers.teams_bot as tb
        real_send, real_cfg = tb.send_personal, tb.is_configured
        sent = []
        tb.is_configured = lambda *a, **k: True
        tb.send_personal = lambda u, activity, cfg=None: sent.append(u)
        orig = frappe.conf.get("ec_approval_teams_disabled")
        frappe.conf.ec_approval_teams_disabled = 0
        try:
            engine._send_teams_batch(["a@x.com", "b@x.com", "Guest", None], "subj", "EC Approval Type", "X")
        finally:
            tb.send_personal, tb.is_configured = real_send, real_cfg
            frappe.conf.ec_approval_teams_disabled = orig
        self.assertEqual(set(sent), {"a@x.com", "b@x.com"})   # Guest/None skipped

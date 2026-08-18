# Copyright (c) 2026, eCentric and contributors
"""engine.notify routes every approval notification through the notification_center pipeline
(events.publish_notification_event), which owns the in-app log AND fans out to the working
'eCentric Copilot' Teams channel. Verifies event_type + per-recipient dispatch + Guest/None skip."""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.engine import service as engine


class TestNotifyRouting(FrappeTestCase):
    def test_notify_publishes_approval_required_per_recipient(self):
        from ecentric_workspace.notification_center import events as ncev
        calls = []
        real = ncev.publish_notification_event
        ncev.publish_notification_event = lambda *a, **k: calls.append((a, k)) or {"ok": True}
        try:
            engine.notify(["a@x.com", "b@x.com", "Guest", None], "Approval needed: X",
                          "EC Approval Type", "X")
        finally:
            ncev.publish_notification_event = real
        recipients = {a[1] for a, k in calls}
        self.assertEqual(recipients, {"a@x.com", "b@x.com"})      # Guest/None skipped
        for a, k in calls:
            self.assertEqual(a[0], "approval_required")           # event_type -> teams ON by default
            self.assertEqual(a[2], "Approval needed: X")          # title
            self.assertEqual(k.get("reference_doctype"), "EC Approval Type")
            self.assertIn("dedupe_key", k)                        # unique -> never wrongly suppressed

    def test_notify_never_raises_on_pipeline_error(self):
        from ecentric_workspace.notification_center import events as ncev
        real = ncev.publish_notification_event

        def boom(*a, **k):
            raise RuntimeError("provider down")

        ncev.publish_notification_event = boom
        try:
            engine.notify(["a@x.com"], "subj", "EC Approval Type", "X")   # must not raise
        finally:
            ncev.publish_notification_event = real

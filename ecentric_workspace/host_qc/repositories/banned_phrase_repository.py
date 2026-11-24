# Copyright (c) 2026, eCentric and contributors
"""Host QC Banned Phrase - tu cam theo san dung chung moi phien."""
import frappe

from ecentric_workspace.host_qc.constants import doctypes as DT


class BannedPhraseRepository:
    def for_platform(self, platform):
        return frappe.get_all(DT.BANNED, filters={"enabled": 1, "platform": ["in", ["all", platform or "all"]]},
                              fields=["kind", "phrase"], order_by="phrase asc")

# Copyright (c) 2026, eCentric and contributors
"""p027_create_asset_damage_loss_page: create the Asset Damage or Loss Web Page at route
/approvals/asset-damage-loss from source (run-once at migrate). Delegates to
asset_damage_loss.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.asset_damage_loss import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p027_create_asset_damage_loss_page: %s" % (res or {}))

# Copyright (c) 2026, eCentric and contributors
"""Job nen (frappe.enqueue tu StartBuildKitService): gui file Bo live sang may chay video. Idempotent - file da
gui (state.rels) bo qua; Bo live khong o trang thai Dang gui thi bo qua."""
import frappe


def run(kit):
    from ecentric_workspace.ai_tools.features.ai_live.application.send_kit_service import SendKitService
    frappe.logger("ai_live").info("send_kit start %s" % kit)
    res = SendKitService().execute(kit)
    frappe.db.commit()
    frappe.logger("ai_live").info("send_kit end %s %s" % (kit, res))

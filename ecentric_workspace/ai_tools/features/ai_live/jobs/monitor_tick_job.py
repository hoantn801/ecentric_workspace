# Copyright (c) 2026, eCentric and contributors
"""Cron moi phut: quet tin hieu may phat AI Live -> bao dong Teams / Zalo (mat tin hieu, nang muc, co lai).
Idempotent (chong lap theo khoa + 10 phut). Tat bang site_config ec_ai_live_monitor_disabled = 1."""
import frappe

from ecentric_workspace.ai_tools.features.ai_live import constants as C


def run():
    if frappe.conf.get(C.KILL_SWITCH):
        return
    from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
    from ecentric_workspace.ai_tools.features.ai_live.application.monitor_tick_service import MonitorTickService
    log = frappe.logger("ai_live")
    svc = MonitorTickService(link=frappe.utils.get_url().rstrip("/") + C.MONITOR_LINK, reports=D.slot_reports())
    rows, sent, failed = svc.targets(), 0, 0
    log.info("ai_live monitor tick: start (%d live)" % len(rows))
    for row in rows:
        try:
            sent += svc.check(row)
            frappe.db.commit()
        except Exception:
            failed += 1
            frappe.db.rollback()
            frappe.log_error(title="ai_live monitor tick: %s" % row.get("key"))
    try:
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        svc.purge(commands=DS.commands(), logs=DS.logs())
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="ai_live monitor purge")
    log.info("ai_live monitor tick: done (sent %d, failed %d)" % (sent, failed))

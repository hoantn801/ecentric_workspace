# Copyright (c) 2026, eCentric and contributors
"""Cron moi phut (W17): may AI Live im lang qua N phut khi dang co live -> bao KHAN Teams / Zalo, nhac lai,
bao lien lac lai. Idempotent (moc watch_* tren EC AI Live Machine). Tat cung ca giam sat bang site_config
ec_ai_live_monitor_disabled = 1."""
import frappe

from ecentric_workspace.ai_tools.features.ai_live import constants as C


def run():
    if frappe.conf.get(C.KILL_SWITCH):
        return
    from ecentric_workspace.ai_tools.features.ai_live.application.watch_machines_service import WatchMachinesService
    log = frappe.logger("ai_live")
    svc = WatchMachinesService(link=frappe.utils.get_url().rstrip("/") + C.MONITOR_LINK)
    rows, sent, failed = svc.targets(), 0, 0
    log.info("ai_live watch machines: start (%d may)" % len(rows))
    for m in rows:
        try:
            sent += svc.check(m)
            frappe.db.commit()
        except Exception:
            failed += 1
            frappe.db.rollback()
            frappe.log_error(title="ai_live watch machines: %s" % m.get("machine_code"))
    log.info("ai_live watch machines: done (sent %d, failed %d)" % (sent, failed))

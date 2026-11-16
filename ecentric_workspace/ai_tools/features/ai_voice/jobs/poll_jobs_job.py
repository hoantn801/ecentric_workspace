# Copyright (c) 2026, eCentric and contributors
"""Cron 2 phut: luoi an toan khi callback khong toi + doi chieu giong dang tao tren may.
Idempotent; moi phieu 1 giao dich rieng (1 phieu loi khong chan phieu khac). Khong co phieu dang chay
thi chi 1 truy van rong. Tat khan: site_config `ec_ai_voice_disabled: 1`."""
import frappe

from ecentric_workspace.ai_tools.features.ai_voice.jobs._common import disabled, guarded


def run():
    if disabled():
        return
    from ecentric_workspace.ai_tools.features.ai_voice.application.poll_jobs_service import PollJobsService
    from ecentric_workspace.ai_tools.features.ai_voice.application.sync_voices_service import SyncVoicesService
    log = frappe.logger("ai_voice")
    svc = PollJobsService()
    names = svc.targets()
    if names:
        log.info("ai_voice poll: start (%d phieu)" % len(names))
    done = 0
    for name in names:
        if guarded("poll " + str(name), lambda n=name: svc.process(n)) is not None:
            done += 1
    n = guarded("reconcile voices", lambda: SyncVoicesService().reconcile())
    if names or n:
        log.info("ai_voice poll: done (%d/%d phieu, %s giong)" % (done, len(names), n or 0))

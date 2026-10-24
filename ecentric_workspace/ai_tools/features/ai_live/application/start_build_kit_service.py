# Copyright (c) 2026, eCentric and contributors
"""Bam "Dung Bo live": kiem tra du lieu, danh dau Dang gui, day viec gui file sang may chay video ra nen."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common, _deps
from ecentric_workspace.ai_tools.features.ai_live.domain import kit_plan


class StartBuildKitService:
    def __init__(self, kits=None, enqueue=None):
        self.kits = kits or _deps.kits()
        self.enqueue = enqueue

    def execute(self, roles, name):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        kit = self.kits.get(name)
        if not kit:
            raise C.AiLiveError(C.KitMsg.NOT_FOUND % name)
        if kit.get("status") in (C.KitStatus.SENDING, C.KitStatus.BUILDING):
            raise C.AiLiveError(C.KitMsg.BUSY)
        if not kit.get("host_key"):
            raise C.AiLiveError(C.KitMsg.NEED_HOST)
        if not kit_plan.audio_entries(kit.get("products") or [], kit.get("faq") or [], kit.get("generic") or {}):
            raise C.AiLiveError(C.KitMsg.NOTHING)
        st = dict(kit.get("state") or {})
        st.pop("error", None)
        self.kits.save(name, {"status": C.KitStatus.SENDING, "state": st})
        if self.enqueue is None:
            import frappe
            frappe.enqueue("ecentric_workspace.ai_tools.features.ai_live.jobs.send_kit_job.run", queue="long",
                           timeout=1800, kit=name, enqueue_after_commit=True)
        else:
            self.enqueue(name)
        return {"name": name, "status": C.KitStatus.SENDING}

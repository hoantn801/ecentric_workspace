# Copyright (c) 2026, eCentric and contributors
"""Xem 1 Bo live; tick=1 thi hoi may chay video tien do dung va cap nhat trang thai."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common, _deps
from ecentric_workspace.ai_tools.features.ai_live.domain import kit_plan


class GetKitService:
    def __init__(self, kits=None, worker=None):
        self.kits = kits or _deps.kits()
        self.worker = worker or _deps.worker()

    def execute(self, roles, name, tick=False):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        kit = self.kits.get(name)
        if not kit:
            raise C.AiLiveError(C.KitMsg.NOT_FOUND % name)
        st = dict(kit.get("state") or {})
        if tick and kit.get("status") == C.KitStatus.BUILDING and st.get("tasks"):
            tasks = self.worker.call("status", batch_id=C.BATCH_KIT + name).get("tasks") or []
            status, prog = kit_plan.tasks_summary([t for t in tasks if t.get("id") in st["tasks"]])
            st["progress"] = prog
            if status != kit["status"] or prog != (kit.get("state") or {}).get("progress"):
                self.kits.save(name, {"status": status, "state": st})
            kit["status"] = status
        kit["state"] = {k: st.get(k) for k in ("progress", "error", "out", "kit_folder")}
        kit["summary"] = kit_plan.summary(kit.get("products") or [], kit.get("faq") or [], kit.get("generic") or {})
        kit["generic_defaults"] = kit_plan.generic_defaults()
        return kit

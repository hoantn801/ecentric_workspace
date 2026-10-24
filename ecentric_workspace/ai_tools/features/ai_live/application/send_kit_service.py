# Copyright (c) 2026, eCentric and contributors
"""Chay nen: tai voice/nen cua Bo live len may chay video (bo qua file da gui) roi xep viec build_kit."""
import os

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _deps
from ecentric_workspace.ai_tools.features.ai_live.domain import kit_plan


class SendKitService:
    def __init__(self, kits=None, files=None, worker=None, brands=None):
        self.kits = kits or _deps.kits()
        self.files = files or _deps.files()
        self.worker = worker or _deps.worker()
        self.brands = brands or _deps.brands()

    def execute(self, name):
        kit = self.kits.get(name)
        if not kit or kit.get("status") != C.KitStatus.SENDING:
            return {"skipped": True}
        st = dict(kit.get("state") or {})
        rels = dict(st.get("rels") or {})
        try:
            ents = kit_plan.audio_entries(kit["products"], kit["faq"], kit["generic"])
            base = "inbox/kit_%s" % kit_plan.slug(name, 30)
            for label, a in ents:
                if a["file"] not in rels:
                    ext = os.path.splitext(a["file"])[1].lower()
                    rels[a["file"]] = self._up(base, label + ext, a["file"])
                    st["rels"] = rels                            # luu dan: loi giua chung thi lan sau gui tiep
                    self.kits.save(name, {"state": st})
            bg_rel = None
            if kit.get("background"):
                ext = os.path.splitext(kit["background"])[1].lower()
                bg_rel = rels.get(kit["background"]) or self._up(base, "background" + ext, kit["background"])
                rels[kit["background"]] = bg_rel
            cfg = self.brands.get(kit["brand"]) or {}
            kit["brand_name"] = cfg.get("brand_name") or kit["brand"]
            step = kit_plan.build_step(kit, kit["products"], kit["faq"], kit["generic"], rels, bg_rel)
            ids = self.worker.call("enqueue", batch_id=C.BATCH_KIT + name, steps=[step]).get("task_ids") or []
            st.update({"rels": rels, "tasks": ids, "out": step["out"], "kit_folder": cfg.get("kit_folder") or ""})
            self.kits.save(name, {"status": C.KitStatus.BUILDING, "state": st})
            return {"tasks": len(ids)}
        except Exception as e:                                   # job nen: ghi loi de trang hien, khong nem tiep
            st.update({"rels": rels, "error": str(e)[:300] or C.Msg.UNKNOWN})
            self.kits.save(name, {"status": C.KitStatus.ERROR, "state": st})
            return {"error": st["error"]}

    def _up(self, base, fname, file_url):
        content = self.files.content(file_url)
        if content is None:
            raise C.AiLiveError(C.KitMsg.BAD_FILE % file_url)
        return self.worker.upload("%s/%s" % (base, fname), fname, content)

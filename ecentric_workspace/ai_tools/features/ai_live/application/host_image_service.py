# Copyright (c) 2026, eCentric and contributors
"""Studio anh host: tao host moi tu mo ta + anh tham chieu (model chon duoc), ra 4 ung vien khung neo."""
import os
import secrets

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common, _deps
from ecentric_workspace.ai_tools.features.ai_live.domain import kit_plan


class HostImageService:
    def __init__(self, worker=None, files=None, labels=None):
        self.worker = worker or _deps.worker()
        self.files = files or _deps.files()
        self.labels = labels or _deps.labels()

    def execute(self, user, roles, payload):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        d = payload if isinstance(payload, dict) else (_common.parse_json(payload, "Studio") or {})
        prompt = str(d.get("prompt") or "").strip()
        if not prompt:
            raise C.AiLiveError(C.KitMsg.NEED_PROMPT)
        model = str(d.get("model") or "")
        cost = kit_plan.image_cost(model, C.HOST_IMAGE_N)
        refs = [str(u) for u in (d.get("refs") or []) if u][:C.MAX_REFS]
        _deps.check_files(self.files, user, roles, refs)
        host = "H_" + secrets.token_hex(5).upper()
        rels = []
        for i, u in enumerate(refs, 1):
            ext = os.path.splitext(u)[1].lower() or ".png"
            content = self.files.content(u)
            if content is None:
                raise C.AiLiveError(C.KitMsg.BAD_FILE % u)
            rels.append(self.worker.upload("inbox/%s/ref_%d%s" % (host, i, ext), "ref_%d%s" % (i, ext), content))
        step = {"op": "host_image", "host": host, "prompt": prompt[:C.MAX_PROMPT], "refs": rels, "model": model,
                "n": C.HOST_IMAGE_N, "aspect": "9:16"}
        ids = self.worker.call("enqueue", batch_id=C.BATCH_HOST_IMAGE + host, steps=[step]).get("task_ids") or []
        label = str(d.get("label") or "").strip()[:80]
        if label:
            self.labels.set(host, label)
        return {"host": host, "tasks": len(ids), "cost": cost}

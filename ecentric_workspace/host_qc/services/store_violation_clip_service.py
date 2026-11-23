# Copyright (c) 2026, eCentric and contributors
"""violation_clip: nhan mp4 (<= 15 MB) cua 1 loi, luu RIENG TU tren ERP, clip_status = pending.

Dot 2 day len SharePoint (upload session) bang job nen roi xoa ban tam. Gui lai cung clip thi tra trang
thai hien co, khong luu them ban nua."""
from ecentric_workspace.host_qc.constants import doctypes as DT
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.rules import CLIP_MAX_BYTES, CLIP_TYPES
from ecentric_workspace.host_qc.constants.statuses import ClipStatus
from ecentric_workspace.host_qc.exceptions import ForbiddenError, InvalidInput, NotFoundError
from ecentric_workspace.host_qc.repositories.file_repository import FileRepository
from ecentric_workspace.host_qc.repositories.session_repository import SessionRepository
from ecentric_workspace.host_qc.repositories.violation_repository import ViolationRepository


class StoreViolationClipService:
    def __init__(self, violations=None, sessions=None, files=None):
        self.violations = violations or ViolationRepository()
        self.sessions = sessions or SessionRepository()
        self.files = files or FileRepository()

    def execute(self, machine, violation_id, upload):
        v = self.violations.get(str(violation_id or ""))
        if not v:
            raise NotFoundError(M.NO_VIOLATION % violation_id)
        s = self.sessions.get_brief(v["session"])
        if not s or s["machine"] != machine["name"]:
            raise ForbiddenError(M.WRONG_MACHINE)
        if v.get("clip_local_file") or v.get("clip_status") in (ClipStatus.UPLOADED.value, ClipStatus.EXPIRED.value):
            return {"clip_status": v.get("clip_status") or ClipStatus.PENDING.value}
        if not upload or not upload.get("content"):
            raise InvalidInput(M.BAD_FILE)
        if len(upload["content"]) > CLIP_MAX_BYTES:
            raise InvalidInput(M.CLIP_TOO_BIG)
        ctype = (upload.get("content_type") or "").split(";")[0].strip().lower()
        if ctype not in CLIP_TYPES and not str(upload.get("filename") or "").lower().endswith(".mp4"):
            raise InvalidInput(M.CLIP_BAD_TYPE)
        url = self.files.save_private(DT.VIOLATION, v["name"], "clip_local_file", "%s.mp4" % v["name"],
                                      upload["content"])
        self.violations.update(v["name"], {"clip_local_file": url, "clip_status": ClipStatus.PENDING.value})
        return {"clip_status": ClipStatus.PENDING.value}

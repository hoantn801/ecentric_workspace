# Copyright (c) 2026, eCentric and contributors
"""session_close: phien -> Closed, luu tom tat / de xuat / chep loi (.jsonl.gz, tuy chon) va diem.

Chep loi dot 1 luu rieng tu tren ERP; dot 2 chuyen len SharePoint. Gui lai: khong luu chep loi lan 2."""
import json

from ecentric_workspace.host_qc.constants import doctypes as DT
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.rules import TEXT_MAX, TRANSCRIPT_MAX_BYTES
from ecentric_workspace.host_qc.constants.statuses import SessionStatus
from ecentric_workspace.host_qc.exceptions import ForbiddenError, InvalidInput, NotFoundError
from ecentric_workspace.host_qc.repositories.file_repository import FileRepository
from ecentric_workspace.host_qc.repositories.machine_repository import MachineRepository
from ecentric_workspace.host_qc.repositories.session_repository import SessionRepository
from ecentric_workspace.host_qc.services.rescore_session_service import RescoreSessionService
from ecentric_workspace.host_qc.utils.time import now, to_dt


class CloseSessionService:
    def __init__(self, sessions=None, machines=None, files=None, rescore=None, clock=now):
        self.sessions = sessions or SessionRepository()
        self.machines = machines or MachineRepository()
        self.files = files or FileRepository()
        self.rescore = rescore or RescoreSessionService(sessions=self.sessions)
        self.clock = clock

    def execute(self, machine, payload, transcript=None):
        sid = str(payload.get("session_id") or "")
        s = self.sessions.get_full(sid)
        if not s:
            raise NotFoundError(M.NO_SESSION % sid)
        if s["machine"] != machine["name"]:
            raise ForbiddenError(M.WRONG_MACHINE)
        recs = payload.get("recommendations")
        vals = {"status": SessionStatus.CLOSED.value,
                "ended_at": to_dt(payload.get("ended_at")) or self.clock(),
                "summary": str(payload.get("summary") or s.get("summary") or "")[:TEXT_MAX * 10],
                "recommendations": ("\n".join(str(x) for x in recs) if isinstance(recs, list) else str(recs or ""))[:TEXT_MAX]}
        if isinstance(payload.get("score"), dict):
            vals["app_score_json"] = json.dumps(payload["score"], ensure_ascii=False)[:20000]
        if transcript and transcript.get("content") and not s.get("transcript_file"):
            if len(transcript["content"]) > TRANSCRIPT_MAX_BYTES:
                raise InvalidInput(M.TRANSCRIPT_TOO_BIG)
            vals["transcript_file"] = self.files.save_private(DT.SESSION, sid, "transcript_file",
                                                              "%s.transcript.jsonl.gz" % sid, transcript["content"])
        self.sessions.update(sid, vals)
        if self.machines.current_session(machine["name"]) == sid:
            self.machines.set_current_session(machine["name"], None)
        self.rescore.execute(sid)
        return {}

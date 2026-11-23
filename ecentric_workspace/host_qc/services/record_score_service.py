# Copyright (c) 2026, eCentric and contributors
"""score: app gui ScoreState tam trong phien. ERP luu ban cua app de doi chieu (app_score_json) roi tinh
lai diem tu loi tren ERP - nguon diem la ERP vi chi ERP biet ket qua duyet cua QC."""
import json

from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.exceptions import ForbiddenError, NotFoundError
from ecentric_workspace.host_qc.repositories.session_repository import SessionRepository
from ecentric_workspace.host_qc.services.rescore_session_service import RescoreSessionService


class RecordScoreService:
    def __init__(self, sessions=None, rescore=None):
        self.sessions = sessions or SessionRepository()
        self.rescore = rescore or RescoreSessionService(sessions=self.sessions)

    def execute(self, machine, session_id, score):
        s = self.sessions.get_brief(str(session_id or ""))
        if not s:
            raise NotFoundError(M.NO_SESSION % session_id)
        if s["machine"] != machine["name"]:
            raise ForbiddenError(M.WRONG_MACHINE)
        if isinstance(score, dict):
            self.sessions.update(s["name"], {"app_score_json": json.dumps(score, ensure_ascii=False)[:20000]})
        self.rescore.execute(s["name"])
        return {}

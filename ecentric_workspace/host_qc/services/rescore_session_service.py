# Copyright (c) 2026, eCentric and contributors
"""Tinh lai diem phien tu cac loi DANG LUU tren ERP (sau moi loi moi / duyet) va ghi vao phien.

ERP la nguon diem: diem app gui (score) chi luu lam doi chieu (app_score_json); tong / mau tren ERP luon
tinh tu loi + ket qua duyet cua QC, bang ComputeScoreService (cung cong thuc voi app)."""
from ecentric_workspace.host_qc.repositories.session_repository import SessionRepository
from ecentric_workspace.host_qc.repositories.violation_repository import ViolationRepository
from ecentric_workspace.host_qc.services.build_rules_config_service import BuildRulesConfigService
from ecentric_workspace.host_qc.services.compute_score_service import ComputeScoreService


class RescoreSessionService:
    def __init__(self, sessions=None, violations=None, rules_config=None, compute=None):
        self.sessions = sessions or SessionRepository()
        self.violations = violations or ViolationRepository()
        self.rules_config = rules_config or BuildRulesConfigService()
        self.compute = compute or ComputeScoreService()

    def execute(self, session_id, rules=None):
        s = self.sessions.get_brief(session_id)
        if not s:
            return None
        rules = rules or self.rules_config.execute()
        sc = self.compute.execute(self.violations.for_scoring(session_id), rules, t0=s.get("started_at"))
        g = sc["groups"]
        self.sessions.update(session_id, {
            "total_score": sc["total"], "status_color": sc["status"],
            "score_a": g.get("A", {}).get("score"), "score_b": g.get("B", {}).get("score"),
            "score_c": g.get("C", {}).get("score"), "score_d": g.get("D", {}).get("score"),
            "minor_count": sc["counts"]["Minor"], "major_count": sc["counts"]["Major"],
            "critical_count": sc["counts"]["Critical"], "needs_verification": 1 if sc["needs_verification"] else 0,
            "score_explain": "\n".join(sc["explain"])})
        return sc

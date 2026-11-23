# Copyright (c) 2026, eCentric and contributors
"""Trang "Bang huong dan" (chi doc cho moi role Host QC): ma, nhom, muc, cach phat hien, nguong dang ap
dung, meo chinh + cac muc chung. can_edit chi true voi Host QC Manager."""
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.roles import MANAGE, VIEW
from ecentric_workspace.host_qc.exceptions import ForbiddenError
from ecentric_workspace.host_qc.repositories.rule_repository import RuleRepository
from ecentric_workspace.host_qc.repositories.settings_repository import SettingsRepository
from ecentric_workspace.host_qc.services.build_rules_config_service import BuildRulesConfigService, num


class GetGuideService:
    def __init__(self, settings=None, rules=None):
        self.settings = settings or SettingsRepository()
        self.rules = rules or RuleRepository()

    def execute(self, roles):
        if not set(roles or ()) & set(VIEW):
            raise ForbiddenError(M.NEED_VIEWER)
        cfg = BuildRulesConfigService(self.settings, self.rules).execute()
        rows = []
        for r in self.rules.list_all(cfg["version"]):
            rows.append({k: r.get(k) for k in ("code", "title", "group", "enabled", "severity", "default_review",
                                                "deduct_only_valid", "how", "default_text", "tune_tip")}
                        | {"params": [dict(p, value=num(p.get("value"))) for p in r.get("params") or []],
                           "format_overrides": [dict(o, value=num(o.get("value"))) for o in r.get("format_overrides") or []]})
        return {"can_edit": bool(set(roles or ()) & set(MANAGE)), "version": cfg["version"], "rows": rows,
                "groups": cfg["groups"], "deduction": cfg["deduction"], "status": cfg["status"],
                "alert": cfg["alert"], "evidence": cfg["evidence"]}

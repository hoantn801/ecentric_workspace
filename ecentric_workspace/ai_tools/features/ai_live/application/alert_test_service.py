# Copyright (c) 2026, eCentric and contributors
"""Quan tri bam "Gui thu": gui 1 tin thu ra Teams / Zalo theo EC AI Live Alert Settings, tra ket qua tung kenh."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R


class AlertTestService:
    def __init__(self, settings=None, sender=None, link=""):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        self.settings = settings or D.settings()
        self.sender = sender or D.sender()
        self.link = link

    def execute(self, roles):
        _common.require_role(roles, C.ADMIN_ROLES, C.Msg.NEED_ADMIN)
        cfg = self.settings.get(with_secrets=True)
        if not (cfg.get("teams_enabled") or cfg.get("zalo_enabled")):
            raise C.AiLiveError(C.MonMsg.NO_CHANNEL)
        title, body = R.format_alert(C.Level.INFO, {"brand": "Thử"}, C.MonMsg.TEST_TEXT)
        t_ok, t_code = self.sender.send_teams(cfg, C.Level.INFO, title, body, self.link)
        z_ok, z_code = self.sender.send_zalo(cfg, title, body, self.link)
        return {"teams": {"ok": t_ok, "code": t_code}, "zalo": {"ok": z_ok, "code": z_code}}

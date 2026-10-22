# Copyright (c) 2026, eCentric and contributors
"""Quan tri bam "Gui thu": gui 1 tin thu ra Teams / Zalo theo EC AI Live Alert Settings, tra ket qua tung kenh."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application._alert_send import send_routed
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R


def _ok(code):
    return str(code).isdigit() and 200 <= int(code) < 300


class AlertTestService:
    def __init__(self, settings=None, sender=None, link=""):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        self.settings = settings or D.settings()
        self.sender = sender or D.sender()
        self.link = link

    def execute(self, roles):
        _common.require_role(roles, C.ADMIN_ROLES, C.Msg.NEED_ADMIN)
        cfg = self.settings.get(with_secrets=True)
        groups = [g for g in cfg.get("channels") or [] if g.get("enabled") and (g.get("teams_enabled") or g.get("zalo_enabled"))]
        if not (cfg.get("teams_enabled") or cfg.get("zalo_enabled") or groups):
            raise C.AiLiveError(C.MonMsg.NO_CHANNEL)
        title, body = R.format_alert(C.Level.INFO, {"brand": "Thử"}, C.MonMsg.TEST_TEXT)
        res = send_routed(self.sender, cfg, C.Level.INFO, title, body, self.link, [], all_groups=True)
        (_, t_code, z_code), rest = res[0], res[1:]               # fix10f: kenh chung + tung nhom brand
        return {"teams": {"ok": _ok(t_code), "code": t_code}, "zalo": {"ok": _ok(z_code), "code": z_code},
                "groups": [{"group": g, "teams": t, "zalo": z} for g, t, z in rest]}

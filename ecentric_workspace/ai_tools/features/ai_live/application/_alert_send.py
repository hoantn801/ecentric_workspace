# Copyright (c) 2026, eCentric and contributors
"""Gui 1 tin bao dong ra moi kenh phu hop (kenh chung + nhom theo brand) - dung chung cho quet tung live,
quet may im lang va nut Gui thu. sender: module infrastructure.alert_channels (test truyen ban gia)."""
from ecentric_workspace.ai_tools.features.ai_live.domain import alert_routing as A


def send_routed(sender, cfg, level, title, body, link, brands, all_groups=False, escalation=False):
    """-> [(nhom, ma Teams, ma Zalo)]; nhom "" = kenh chung. Khong tra / khong ghi URL hay token."""
    out = []
    for ch in A.channels_for(cfg, brands, all_groups, escalation):
        _, t_code = sender.send_teams(ch, level, title, body, link)
        _, z_code = sender.send_zalo(ch, title, body, link)
        out.append((ch["group"], t_code, z_code))
    return out

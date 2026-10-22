# Copyright (c) 2026, eCentric and contributors
"""Chon kenh bao dong (W17, thuan Python): kenh chung trong EC AI Live Alert Settings luon nhan (neu bat),
cong them cac nhom trong bang "Kenh theo nhom / brand" co brand trung (nhom de trong brand = nhan moi bao dong).
Cung mot webhook / mot nhom Zalo chi gui 1 lan."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C

_COMMON = ("teams_format", "zalo_api_base", "zalo_send_path", "zalo_bot_token")


def brand_set(text_or_list):
    items = text_or_list if isinstance(text_or_list, (list, tuple)) else str(text_or_list or "").replace(",", "\n").splitlines()
    return {str(b).strip().lower() for b in items if str(b).strip()}


def channels_for(cfg, brands, all_groups=False):
    """-> [cfg kenh] (cung khoa voi cfg chung: teams_enabled, teams_webhook_url, teams_format, zalo_enabled,
    zalo_bot_token, zalo_chat_id, zalo_api_base, zalo_send_path, group). all_groups: gui thu moi nhom."""
    want, out = brand_set(brands), [dict(cfg, group="")]
    for g in cfg.get("channels") or []:
        if not g.get("enabled"):
            continue
        gb = brand_set(g.get("brands"))
        if all_groups or not gb or gb & want:
            ch = {k: (g.get(k) or cfg.get(k) or "") for k in _COMMON}
            ch.update({"teams_enabled": int(g.get("teams_enabled") or 0), "teams_webhook_url": g.get("teams_webhook_url") or "",
                       "zalo_enabled": int(g.get("zalo_enabled") or 0), "zalo_chat_id": g.get("zalo_chat_id") or "",
                       "group": g.get("group_name") or "?"})
            out.append(ch)
    return _dedupe(out)


def _dedupe(chans):
    seen_t, seen_z, out = set(), set(), []
    for ch in chans:
        ch = dict(ch)
        t = ch.get("teams_webhook_url") if ch.get("teams_enabled") else ""
        z = (ch.get("zalo_bot_token"), ch.get("zalo_chat_id")) if ch.get("zalo_enabled") else None
        if t in seen_t:
            ch["teams_enabled"] = 0
        if z in seen_z:
            ch["zalo_enabled"] = 0
        seen_t.add(t or None)
        seen_z.add(z)
        out.append(ch)
    return out


def result_text(results):
    """[(group, teams_code, zalo_code)] -> ('200,OFF', '200') cho cot ket qua (bo kenh OFF o nhom phu)."""
    t = [("%s:" % g if g else "") + tc for g, tc, _ in results if not g or tc != "OFF"]
    z = [("%s:" % g if g else "") + zc for g, _, zc in results if not g or zc != "OFF"]
    return ",".join(t)[:C.MAX_ALERT_TEXT // 2], ",".join(z)[:C.MAX_ALERT_TEXT // 2]

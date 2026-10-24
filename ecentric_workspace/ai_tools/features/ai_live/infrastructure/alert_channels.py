# Copyright (c) 2026, eCentric and contributors
"""Gui tin bao dong AI Live ra Microsoft Teams (incoming webhook / Workflows) va Zalo Bot.
Khong log URL webhook / token. Moi ham tra (ok, ma_ket_qua) - ma la so HTTP, "EXC:<loai loi>" hoac "OFF"."""
import json

from ecentric_workspace.ai_tools.features.ai_live import constants as C

_COLOR = {C.Level.CRIT: ("attention", "D13438"), C.Level.OFF: ("attention", "D13438"),
          C.Level.WARN: ("warning", "FFB900"), C.Level.INFO: ("good", "17683A"), C.Level.OK: ("good", "17683A")}


def teams_payload(fmt, level, title, text, link):
    color, hexc = _COLOR.get(level, _COLOR[C.Level.WARN])
    if fmt == "messagecard":
        card = {"@type": "MessageCard", "@context": "https://schema.org/extensions", "summary": title,
                "themeColor": hexc, "sections": [{"activityTitle": title, "text": text}]}
        if link:
            card["potentialAction"] = [{"@type": "OpenUri", "name": "Mở màn Giám sát",
                                        "targets": [{"os": "default", "uri": link}]}]
        return card
    content = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4",
               "body": [{"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "color": color, "wrap": True},
                        {"type": "TextBlock", "text": text, "wrap": True}]}
    if link:
        content["actions"] = [{"type": "Action.OpenUrl", "title": "Mở màn Giám sát", "url": link}]
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive",
                                                 "contentUrl": None, "content": content}]}


def _post(url, payload):
    import requests
    try:
        r = requests.post(url, data=json.dumps(payload), headers={"Content-Type": "application/json"},
                          timeout=C.HTTP_TIMEOUT)
    except Exception as e:  # mang / DNS / timeout: khong lam hong ca lan quet
        return False, "EXC:" + type(e).__name__, None
    body = None
    try:
        body = r.json()
    except ValueError:
        pass
    return 200 <= r.status_code < 300, str(r.status_code), body


def send_teams(cfg, level, title, text, link):
    if not (cfg.get("teams_enabled") and cfg.get("teams_webhook_url")):
        return False, "OFF"
    ok, code, _ = _post(cfg["teams_webhook_url"], teams_payload(cfg.get("teams_format"), level, title, text, link))
    return ok, code


def send_zalo(cfg, title, text, link):
    if not (cfg.get("zalo_enabled") and cfg.get("zalo_bot_token") and cfg.get("zalo_chat_id")):
        return False, "OFF"
    url = str(cfg.get("zalo_api_base") or C.ZALO_API_BASE).rstrip("/") + \
        str(cfg.get("zalo_send_path") or C.ZALO_SEND_PATH).replace("{token}", cfg["zalo_bot_token"])
    msg = "%s\n%s" % (title, text) + ("\n%s" % link if link else "")
    ok, code, body = _post(url, {"chat_id": cfg["zalo_chat_id"], "text": msg[:2000]})
    if ok and isinstance(body, dict) and body.get("ok") is False:
        return False, "API:%s" % str(body.get("error_code") or body.get("description") or "false")[:40]
    return ok, code

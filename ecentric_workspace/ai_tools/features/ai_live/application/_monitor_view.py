# Copyright (c) 2026, eCentric and contributors
"""Dung chung cho man Giam sat (thuan Python): bien 1 ban ghi + ket qua danh gia thanh o tren tuong."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C


def tile(row, ev, last_alert=None):
    return {"key": row["key"], "machine": row.get("machine"), "live": row.get("live"), "brand": row.get("brand") or "",
            "state": row.get("state") or "", "level": ev["level"], "stale_s": ev["stale_s"],
            "reasons": [{"code": r["code"], "level": r["level"], "text": r["text"]} for r in ev["reasons"][:4]],
            "metrics": row.get("metrics") or {}, "last_seen_ts": row.get("last_seen_ts"),
            "thumbs": {k: row.get(k + "_thumb_ts") or 0 for k in C.THUMB_KINDS},
            "app_version": row.get("app_version") or "", "last_alert": last_alert}


def bucket(level):
    """Gop muc de dem / loc: critical + offline = do."""
    return C.Level.CRIT if level in (C.Level.CRIT, C.Level.OFF) else level

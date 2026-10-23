# Copyright (c) 2026, eCentric and contributors
"""Ham dung chung cua cac service AI Live (thuan Python, khong goi DB)."""
import json

from ecentric_workspace.ai_tools.features.ai_live import constants as C


def machine_brands(machine):
    """Danh sach brand giao cho may (moi dong 1 ma brand)."""
    return [b.strip() for b in str((machine or {}).get("brands") or "").replace(",", "\n").splitlines() if b.strip()]


def require_machine(repo, user, code=None):
    m = repo.by_user(user)
    if not m or not m.get("enabled"):
        raise C.AiLivePermission(C.Msg.NOT_MACHINE)
    if code is not None and str(code) != m["machine_code"]:
        raise C.AiLivePermission(C.Msg.WRONG_MACHINE)
    return m


def require_role(roles, allowed, msg):
    if not set(roles or ()) & set(allowed):
        raise C.AiLivePermission(msg)


def parse_json(value, label):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    if len(value.encode("utf-8")) > C.MAX_SETTING_BYTES:
        raise C.AiLiveError(C.Msg.TOO_BIG % label)
    try:
        return json.loads(value)
    except ValueError:
        raise C.AiLiveError(C.Msg.BAD_JSON % label)


def id_list(v):
    """fix10g: danh sach ma tu JSON '["a","b"]', chuoi "a,b" hoac list -> list chuoi khong rong."""
    if isinstance(v, str) and v.strip().startswith("["):
        v = parse_json(v, "danh sách")
    if isinstance(v, str):
        v = v.split(",")
    return [str(x).strip() for x in (v or []) if str(x).strip()]

# Copyright (c) 2026, eCentric and contributors
"""Cua vao 2 API khach (license_request / license_checkin): gioi han tan suat theo IP + doc body JSON <= 32 KB.
Redis loi -> cho qua (khong bao gio vi gioi han ma lam app bi khoa: app coi 429 la loi mang)."""
import json
import time

from ecentric_workspace.ai_tools.features.ai_live import license_constants as L


def client_ip():
    import frappe
    return str(getattr(frappe.local, "request_ip", "") or "")[:64]


def over_limit(endpoint, ip, limit, now=None):
    import frappe
    now = time.time() if now is None else now
    try:
        cache = frappe.cache()
        key = cache.make_key("eclic_rl:%s:%s:%d" % (endpoint, ip or "-", int(now // L.RATE_WINDOW_S)))
        n = cache.incrby(key, 1)
        if n == 1:
            cache.expire(key, L.RATE_WINDOW_S * 2)
        return int(n) > limit
    except Exception:
        return False


def read_body():
    """-> dict (hoac gia tri JSON khac - service tu kiem kieu). Qua 32 KB / khong phai JSON -> None."""
    import frappe
    req = frappe.request
    if req is None:
        return None
    if (req.content_length or 0) > L.MAX_BODY:
        return None
    raw = req.get_data(cache=True) or b""
    if len(raw) > L.MAX_BODY:
        return None
    try:
        return json.loads(raw.decode("utf-8")) if raw.strip() else None
    except (ValueError, UnicodeDecodeError):
        return None

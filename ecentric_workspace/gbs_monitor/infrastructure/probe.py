# Copyright (c) 2026, eCentric and contributors
"""Goi mang: IP goi ra + goi thu boxme. Khong ghi gi."""

import requests

from ecentric_workspace.gbs_monitor import constants as C
from ecentric_workspace.gbs_monitor.domain import valid_ip


def egress_ip(http=requests):
    for url in C.IP_SERVICES:
        try:
            r = http.get(url, timeout=C.TIMEOUT)
            if r.status_code != 200:
                continue
            txt = (r.text or "").strip()
            ip = txt
            if txt.startswith("{"):
                ip = str((r.json() or {}).get("ip") or "")
            if valid_ip(ip):
                return ip.strip()
        except Exception:
            continue
    return ""


def boxme_whoami(http=requests):
    """(http_code, user). http_code = 0 khi khong ket noi duoc."""
    from ecentric_workspace.gbs_comment_proxy import _get_gbs_credentials
    base, key, secret = _get_gbs_credentials()
    try:
        r = http.get(base + C.BOXME_WHOAMI, headers={"Authorization": "token " + key + ":" + secret,
                                                     "Accept": "application/json"}, timeout=C.TIMEOUT)
    except Exception:
        return 0, ""
    user = ""
    if r.status_code == 200:
        try:
            user = (r.json() or {}).get("message") or ""
        except Exception:
            user = ""
    return r.status_code, user

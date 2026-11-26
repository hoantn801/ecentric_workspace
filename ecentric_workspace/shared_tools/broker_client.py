# Copyright (c) 2026, eCentric and contributors
"""Goi broker tren may 24/7 (container `broker`, cong 8088, mo ra qua Cloudflare Tunnel o duong
/ec/* cua kalodata-gw.ecentric.asia). Khong co Cloudflare Access -> moi request ky HMAC.

Cau hinh o site_config (KHONG o repo, KHONG in ra log):
  ec_kalodata_broker_url    = "https://kalodata-gw.ecentric.asia/ec"
  ec_kalodata_broker_secret = "<chuoi ngau nhien>"   (giong EC_BROKER_SECRET trong .env may 24/7)

Chu ky: X-EC-Sig = hex HMAC-SHA256(secret, METHOD \\n PATH \\n TS \\n NONCE \\n sha256hex(body))
  PATH = duong dan phia broker (vd /ec/grant), TS = giay unix (lech <= 60 s), NONCE dung mot lan.
Broker:
  POST   /ec/grant   {"user", "ttl"} -> {"ok", "url"}   (xoay mat khau VNC, link Guacamole song ttl giay)
  POST   /ec/revoke                  -> {"ok"}
  GET    /ec/status                  -> {"ok", "vnc_clients", "x_idle_ms", "current_user", "exports_pending"}
  GET    /ec/exports                 -> {"ok", "exports": [meta]}
  GET    /ec/exports/<id>            -> bytes, header X-EC-Export-Meta (JSON)
  DELETE /ec/exports/<id>            -> {"ok"}
URL tra ve tu /ec/grant chua blob dang nhap: chi dua cho DUNG nguoi bam nut, khong ghi log / DB.
"""
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlsplit

import frappe
import requests

from ecentric_workspace.shared_tools import constants as C

TIMEOUT = 15


class HostDown(Exception):
    """Khong noi chuyen duoc voi may 24/7 (tat may, Docker chua chay, tunnel rot)."""


def configured():
    return bool(frappe.conf.get(C.CONF_BROKER_URL) and frappe.conf.get(C.CONF_BROKER_SECRET))


def _conf():
    url = (frappe.conf.get(C.CONF_BROKER_URL) or "").rstrip("/")
    sec = frappe.conf.get(C.CONF_BROKER_SECRET) or ""
    if not url or not sec:
        raise HostDown("Chưa cấu hình máy Kalodata (%s / %s trong site_config)."
                       % (C.CONF_BROKER_URL, C.CONF_BROKER_SECRET))
    return url, sec


def sign(secret, method, path, ts, nonce, body):
    msg = "\n".join([method.upper(), path, str(ts), nonce, hashlib.sha256(body or b"").hexdigest()])
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _request(method, sub, payload=None, raw=False, timeout=TIMEOUT):
    base, sec = _conf()
    url = base + sub
    body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else b""
    ts, nonce = int(time.time()), secrets.token_hex(16)
    headers = {"X-EC-Ts": str(ts), "X-EC-Nonce": nonce,
               "X-EC-Sig": sign(sec, method, urlsplit(url).path, ts, nonce, body)}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    try:
        r = requests.request(method, url, data=body or None, headers=headers, timeout=timeout)
    except requests.RequestException:
        raise HostDown("Không kết nối được máy Kalodata (máy tắt, Docker chưa chạy hoặc tunnel rớt).")
    if r.status_code in (502, 503, 504, 530):
        raise HostDown("Máy Kalodata không phản hồi (HTTP %s)." % r.status_code)
    if r.status_code == 401:
        raise HostDown("Máy Kalodata từ chối chữ ký (sai %s hoặc lệch giờ)." % C.CONF_BROKER_SECRET)
    if raw:
        if r.status_code != 200:
            raise HostDown("Không tải được file từ máy Kalodata (HTTP %s)." % r.status_code)
        return r.content, r.headers
    try:
        data = r.json()
    except ValueError:
        raise HostDown("Máy Kalodata trả dữ liệu lạ (HTTP %s)." % r.status_code)
    if not data.get("ok"):
        raise HostDown("Máy Kalodata báo lỗi: %s" % (data.get("error") or r.status_code))
    return data


def grant(user, ttl=C.LINK_TTL_SEC):
    return _request("POST", "/grant", {"user": user, "ttl": int(ttl)})["url"]


def revoke():
    return _request("POST", "/revoke", {})


def status():
    return _request("GET", "/status", timeout=8)


def exports():
    return _request("GET", "/exports").get("exports") or []


def export_get(export_id):
    content, headers = _request("GET", "/exports/" + export_id, raw=True, timeout=60)
    try:
        meta = json.loads(headers.get("X-EC-Export-Meta") or "{}")
    except ValueError:
        meta = {}
    return content, meta


def export_delete(export_id):
    return _request("DELETE", "/exports/" + export_id)

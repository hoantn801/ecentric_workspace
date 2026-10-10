# Copyright (c) 2026, eCentric and contributors
"""Goi worker video (n8n tren may local, mo ra qua Cloudflare Tunnel).

Cau hinh o site_config (KHONG o repo, KHONG in ra log):
  ec_video_worker_url    = "https://<ten-tunnel>"      (khong co / cuoi)
  ec_video_worker_secret = "<chuoi ngau nhien>"        (giong EC_WORKER_SECRET trong n8n.env)

Worker: POST /webhook/ec-v6/api {action,...}  header X-EC-Secret
        POST /webhook/ec-v6/upload?dest=inbox/<lo>/<ten>  (multipart field "file")
        GET  /webhook/ec-v6/file?p=&e=&s=[&w=]  (link ky HMAC, het han sau ttl)
Worker co the tat (laptop ngu) -> moi loi mang tra WorkerDown de trang bao ro."""
import hashlib
import hmac
import mimetypes
import re
import time
from urllib.parse import urlencode

import frappe
import requests

TIMEOUT = 25


class WorkerDown(Exception):
    pass


LIVE_KEY = "ec_video_worker_url_live"
#: Chi nhan URL tunnel dang nay (quick tunnel cua Cloudflare) hoac dung URL da khai trong site_config.
_TUNNEL_RE = re.compile(r"^https://[a-z0-9-]{3,80}\.trycloudflare\.com$")


def _conf():
    url = (frappe.db.get_default(LIVE_KEY) or frappe.conf.get("ec_video_worker_url") or "").rstrip("/")
    sec = frappe.conf.get("ec_video_worker_secret") or ""
    if not url or not sec:
        raise frappe.ValidationError(
            "Chưa cấu hình worker video (ec_video_worker_url / ec_video_worker_secret trong site_config).")
    return url, sec


def configured():
    return bool((frappe.db.get_default(LIVE_KEY) or frappe.conf.get("ec_video_worker_url"))
                and frappe.conf.get("ec_video_worker_secret"))


def register(url, ts, sig):
    """Worker bao URL tunnel moi (quick tunnel doi URL moi lan khoi dong). Xac thuc bang
    HMAC(secret, url|ts), ts lech <= 10 phut. Tra True neu da ghi."""
    sec = frappe.conf.get("ec_video_worker_secret") or ""
    url = (url or "").strip().rstrip("/")
    if not sec or not url or not ts or not sig:
        return False
    try:
        if abs(time.time() - int(ts)) > 600:
            return False
    except ValueError:
        return False
    exp = hmac.new(sec.encode(), ("%s|%s" % (url, ts)).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(exp, str(sig)):
        return False
    fixed = (frappe.conf.get("ec_video_worker_url") or "").rstrip("/")
    if not (_TUNNEL_RE.match(url) or url == fixed):
        return False
    frappe.db.set_default(LIVE_KEY, url)
    return True


def call(action, **payload):
    url, sec = _conf()
    body = dict(payload, action=action)
    try:
        r = requests.post(url + "/webhook/ec-v6/api", json=body, headers={"X-EC-Secret": sec}, timeout=TIMEOUT)
    except requests.RequestException:
        raise WorkerDown("Không kết nối được máy chạy video (laptop tắt/ngủ hoặc tunnel chưa bật).")
    if r.status_code in (502, 503, 504, 530):
        raise WorkerDown("Máy chạy video không phản hồi (HTTP %s)." % r.status_code)
    try:
        data = r.json()
    except ValueError:
        raise WorkerDown("Worker trả dữ liệu lạ (HTTP %s)." % r.status_code)
    if r.status_code == 401:
        raise frappe.ValidationError("Worker từ chối khoá bí mật (sai ec_video_worker_secret).")
    if not data.get("ok"):
        raise frappe.ValidationError("Worker: %s" % (data.get("error") or "lỗi không rõ"))
    return data


def _mime(filename):
    """n8n (webhook) chi coi mot phan multipart la FILE khi phan do co Content-Type; thieu
    no thi file bi doc thanh chuoi van ban trong body -> worker bao "no file" (01/10)."""
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    if ext == "webp":
        return "image/webp"
    t = mimetypes.guess_type(filename or "")[0]
    return t or "application/octet-stream"


def upload(dest, filename, content):
    """dest: inbox/<lo>/<ten file>. content: bytes."""
    url, sec = _conf()
    try:
        r = requests.post(url + "/webhook/ec-v6/upload", params={"dest": dest}, headers={"X-EC-Secret": sec},
                          files={"file": (filename, content, _mime(filename))}, timeout=120)
    except requests.RequestException:
        raise WorkerDown("Không gửi được file lên máy chạy video.")
    try:
        data = r.json()
    except ValueError:
        raise WorkerDown("Upload lỗi (HTTP %s)." % r.status_code)
    if not data.get("ok"):
        raise frappe.ValidationError("Upload: %s" % (data.get("error") or r.status_code))
    return data["path"]


def fetch(path, timeout=90):
    """Tai 1 file tu worker ve (bytes) qua link ky - vd anh host AI tao de luu thanh File ERP (10/10)."""
    u = sign(path, ttl=600)
    if not u:
        raise WorkerDown("Chưa cấu hình máy chạy video.")
    try:
        r = requests.get(u, timeout=timeout)
    except requests.RequestException:
        raise WorkerDown("Không tải được file từ máy chạy video.")
    if r.status_code != 200 or not r.content:
        raise frappe.ValidationError("Tải file từ máy chạy video lỗi (HTTP %s)." % r.status_code)
    return r.content


def sign(path, ttl=6 * 3600, width=None):
    """Link xem file tren worker. path tuong doi /files (vd 'ecv6/units/X/hold_01.mp4')."""
    if not path or not configured():
        return None
    url, sec = _conf()
    e = str(int(time.time()) + int(ttl))
    s = hmac.new(sec.encode(), ("%s|%s" % (path, e)).encode(), hashlib.sha256).hexdigest()
    q = {"p": path, "e": e, "s": s}
    if width:
        q["w"] = str(int(width))
    return url + "/webhook/ec-v6/file?" + urlencode(q)

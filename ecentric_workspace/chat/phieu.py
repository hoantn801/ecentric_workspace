# Copyright (c) 2026, eCentric and contributors
"""Phieu trong chat - phan THUAN (khong import frappe) de test khong can bench.

  * find_approval_link: tim link phieu ERP dau tien trong noi dung tin nhan Raven (HTML tiptap
    hoac chu thuong) -> (route, id). Chi nhan ten mien ERP va route nam trong danh sach loai phieu.
  * bot_html: noi dung tin nhan bot (HTML Raven render duoc) tu tieu de + tom tat + link.
"""
import html
import re
from urllib.parse import parse_qs, unquote, urlsplit

_URL = re.compile(r"""https?://[^\s"'<>]+""", re.I)
_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<\s*br\s*/?\s*>", re.I)


def norm_route(route):
    """'approvals/x' / '/approvals/x/' -> '/approvals/x'. Rong -> ''."""
    r = (route or "").strip().split("?", 1)[0].strip("/")
    return "/" + r if r else ""


def find_approval_link(text, hosts, routes):
    """(route, id) cua link phieu dau tien, hoac None.
    hosts: tap ten mien ERP (chu thuong). routes: tap route da chuan hoa (norm_route)."""
    if not text or not routes:
        return None
    for m in _URL.finditer(html.unescape(str(text))):
        url = m.group(0).rstrip(".,;:)]}")
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        if (parts.hostname or "").lower() not in hosts:
            continue
        route = norm_route(parts.path)
        if route not in routes:
            continue
        ids = parse_qs(parts.query).get("id") or []
        doc_id = unquote(ids[0]).strip() if ids else ""
        if doc_id and len(doc_id) <= 140:
            return route, doc_id
    return None


def plain_lines(message):
    """HTML tom tat cua transitions.request_summary (<b>, <br>) -> cac dong chu thuong."""
    if not message:
        return []
    text = _BR.sub("\n", str(message))
    text = html.unescape(_TAG.sub("", text))
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def bot_html(title, message, url):
    """Tin nhan bot: tieu de dam, cac dong tom tat, nut chu "Mở phiếu". Moi gia tri deu escape."""
    out = ["<p><strong>%s</strong></p>" % html.escape(title or "Thông báo phê duyệt")]
    lines = plain_lines(message)
    if lines:
        out.append("<p>" + "<br>".join(html.escape(ln) for ln in lines) + "</p>")
    if url and str(url).startswith(("https://", "http://", "/")):
        out.append('<p><a href="%s">Mở phiếu →</a></p>' % html.escape(str(url), quote=True))
    return "".join(out)

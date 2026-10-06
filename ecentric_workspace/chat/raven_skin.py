# Copyright (c) 2026, eCentric and contributors
"""Lop "ruot" cho Raven - phan THUAN (khong import frappe) de test khong can bench.

Hai viec, deu KHONG sua code Raven:

1. Tieng Viet. Raven dich bang ham _() doc window.frappe._messages. Ban 3.0.0 chi gan bien nay
   o che do dev / offline - trang that de trong nen moi chuoi hien tieng Anh. Ta:
     * phu bang dich vao boot["__messages"] cua trang /raven (hook extend_bootinfo, boot.py);
     * chen <script src=ec_raven_boot.js> ngay SAU the <script> boot cua Raven (truoc khi module
       React cua Raven chay - module la defer) de gan frappe._messages = boot.__messages.
2. Mau ERP. Chen <link> ec_chat_raven_skin.css truoc </head>.

Chen vao HTML luc tra response (hook after_request, boot.py), chi voi trang /raven. Khong tim
thay moc (Raven doi template) -> tra None, trang giu nguyen ban goc.
"""
import hashlib
import io
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.dirname(_HERE)
_CACHE = {}
_VER = {}

#: the <script> inline ma raven/www/raven.html dat boot (frappe.boot = JSON.parse("...")).
BOOT_MARK = "frappe.boot = JSON.parse("
SKIN_ID = "ec-raven-skin"
BOOT_ID = "ec-raven-boot"


def is_raven_path(path):
    """True voi /raven va moi duong con /raven/...; KHONG khop /ravenx, /app/raven..."""
    p = (path or "").split("?", 1)[0]
    return p == "/raven" or p.startswith("/raven/")


def load_vi(filename="raven_vi.json"):
    """Doc bang dich mot lan moi tien trinh. Hong tep -> {} (Raven giu tieng Anh)."""
    if filename not in _CACHE:
        try:
            with io.open(os.path.join(_HERE, filename), encoding="utf-8") as fh:
                data = json.load(fh)
            _CACHE[filename] = {k: v for k, v in data.items()
                                if isinstance(k, str) and isinstance(v, str) and v.strip()}
        except Exception:
            _CACHE[filename] = {}
    return _CACHE[filename]


def overlay(messages, vi):
    """Tra dict MOI = messages + vi (vi thang). Khong sua dict cu: boot co the dang nam trong
    bo nho dem cua phien."""
    out = dict(messages or {})
    out.update(vi or {})
    return out


def asset_url(rel):
    """public/x/y.ext -> /assets/ecentric_workspace/x/y.ext?v=<md5 10 ky tu> (doi khi deploy)."""
    if rel not in _VER:
        try:
            with io.open(os.path.join(_APP, rel), "rb") as fh:
                _VER[rel] = hashlib.md5(fh.read()).hexdigest()[:10]
        except Exception:
            _VER[rel] = "0"
    return "/assets/ecentric_workspace/%s?v=%s" % (rel.replace("public/", "", 1), _VER[rel])


def inject_page(html, boot_js, skin_css):
    """Chen script noi ban dich + CSS vao HTML trang /raven. Tra HTML moi, hoac None neu khong
    can / khong the (da chen roi, thieu moc)."""
    if not isinstance(html, str) or SKIN_ID in html or BOOT_ID in html:
        return None
    i = html.find(BOOT_MARK)
    if i < 0:
        return None
    end = html.find("</script>", i)
    head = html.find("</head>")
    if end < 0 or head < 0 or head > i:
        return None
    end += len("</script>")
    script = '<script id="%s" src="%s"></script>' % (BOOT_ID, _attr(boot_js))
    link = '<link id="%s" rel="stylesheet" href="%s">' % (SKIN_ID, _attr(skin_css))
    return html[:head] + link + html[head:end] + script + html[end:]


def _attr(v):
    return (str(v).replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))

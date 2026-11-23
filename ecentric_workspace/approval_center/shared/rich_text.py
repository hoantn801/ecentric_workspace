# Copyright (c) 2026, eCentric and contributors
"""Noi dung soan kieu mail (HTML) dung chung cho moi form approval (23/11/2026).

Client (public/js/ec_richtext.bundle.js) da loc khi dan + khi ve; day la lop LOC CUOI o server -
moi duong ghi (save_draft qua adapter, Desk, API) deu di qua DocType.validate goi ham nay.
  safe_html(html) -> HTML an toan (frappe sanitize_html always_sanitize + bo style/script/iframe...)
  to_text(html)   -> chu tran (tim kiem, tom tat, kiem bat buoc)
"""
import re

_STRIP_RE = re.compile(r"<(style|link|script|iframe|object|embed|svg|math)\b[^>]*>.*?</\1\s*>"
                       r"|<(style|link|script|iframe|object|embed|img|svg|math)\b[^>]*/?>",
                       re.I | re.S)
_EVENT_RE = re.compile(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_JS_URL_RE = re.compile(r"(href|src)\s*=\s*([\"']?)\s*(javascript|vbscript|data):", re.I)
MAX_HTML = 200000


def safe_html(html, limit=MAX_HTML):
    raw = (html or "")[:limit]
    if not raw.strip():
        return ""
    try:
        from frappe.utils.html_utils import sanitize_html
        raw = sanitize_html(raw, always_sanitize=True) or ""
    except Exception:
        pass
    raw = _STRIP_RE.sub("", raw)
    raw = _EVENT_RE.sub("", raw)
    return _JS_URL_RE.sub(r"\1=\2#blocked:", raw)


def to_text(html):
    s = re.sub(r"<\s*br\s*/?>", "\n", html or "", flags=re.I)
    s = re.sub(r"</\s*(p|li|tr|h[1-6]|blockquote|div)\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    try:
        import html as _h
        s = _h.unescape(s)
    except Exception:
        pass
    s = s.replace(" ", " ")
    s = re.sub(r"[ \t]+\n", "\n", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()

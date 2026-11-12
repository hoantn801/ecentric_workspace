# Copyright (c) 2026, eCentric and contributors
"""Lam sach tep .docx truoc khi dua cho trinh xem tren trinh duyet (docx-preview).

docx-preview 0.3.7 ghi thang mot so thuoc tinh cua tep vao trang (QC6 12/11/2026):
  * <w:sym w:char="..."> -> innerHTML "&#x{char};" : char chen the HTML la chay script.
  * Lien ket ngoai (Relationship TargetMode="External") -> <a href> khong kiem giao thuc:
    "javascript:" la link chay script.
Mau do Ke toan tai len, nhung trang xem truoc mo trong phien cua MOI nguoi lap phieu, nen lam
sach o server truoc khi tra ve. Tep tai ve / gui ky KHONG di qua day.
"""
import io
import re
import zipfile

_SYM = re.compile(r"<w:sym\b[^>]*/>|<w:sym\b[^>]*>.*?</w:sym>", re.S)
_SYM_CHAR = re.compile(r'w:char="([^"]*)"')
_HEX = re.compile(r"^[0-9A-Fa-f]{1,4}$")
_REL = re.compile(r"<Relationship\b[^>]*/>", re.S)
_TARGET = re.compile(r'Target="([^"]*)"')
_SAFE_SCHEMES = ("http://", "https://", "mailto:")
_XML_PART = re.compile(r"^word/.*\.xml$")
_RELS_PART = re.compile(r"^word/_rels/.*\.rels$")


def _clean_sym(m):
    c = _SYM_CHAR.search(m.group(0))
    return m.group(0) if c and _HEX.match(c.group(1)) else ""


def _clean_rel(m):
    tag = m.group(0)
    if 'TargetMode="External"' not in tag:
        return tag
    t = _TARGET.search(tag)
    target = (t.group(1) if t else "").strip().lower()
    if target.startswith(_SAFE_SCHEMES):
        return tag
    return _TARGET.sub('Target="#"', tag) if t else tag


def sanitize_for_viewer(data):
    """bytes .docx -> bytes .docx da bo ky hieu sai khuon va lien ket ngoai khong phai http(s)/mailto."""
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            raw = src.read(item.filename)
            if _XML_PART.match(item.filename) and b"<w:sym" in raw:
                raw = _SYM.sub(_clean_sym, raw.decode("utf-8")).encode("utf-8")
            elif _RELS_PART.match(item.filename) and b"External" in raw:
                raw = _REL.sub(_clean_rel, raw.decode("utf-8")).encode("utf-8")
            dst.writestr(item, raw)
    return buf.getvalue()

# Copyright (c) 2026, eCentric and contributors
"""Lam sach tep .docx truoc khi dua cho trinh xem tren trinh duyet (docx-preview).

docx-preview 0.3.7 ghi thang mot so thuoc tinh cua tep vao trang (QC6 12/11/2026):
  * <w:sym w:char="..."> -> innerHTML "&#x{char};" : char chen the HTML la chay script.
  * Lien ket ngoai (Relationship TargetMode="External") -> <a href> khong kiem giao thuc:
    "javascript:" la link chay script.
Mau do Ke toan tai len, nhung trang xem truoc mo trong phien cua MOI nguoi lap phieu, nen lam
sach o server truoc khi tra ve. Tep tai ve / gui ky KHONG di qua day.
"""
import html
import io
import re
import zipfile

# Doc tung THE MO va tung THUOC TINH (ten bat ky tien to, nhay don / kep, dau cach quanh "="), giai
# thuc the (&#69;xternal) roi moi kiem - docx-preview lay thuoc tinh DAU TIEN co ten cuc bo "char" /
# "Target" sau khi trinh duyet giai thuc the (QC 15/11 D7 / A16 / vong 2). Khong khop than phan tu:
# chi sua GIA TRI thuoc tinh trong the mo -> XML luon con hop le, khong backtracking tren tep hong.
# Khoang trang theo XML (space, tab, CR, LF) - KHONG dung \\s cua Python: U+1680... la khoang trang voi
# Python nhung la ky tu ten hop le voi XML -> the bi bo qua ma trinh duyet van doc (QC 15/11 vong 4).
_WS = "[ \\t\\r\\n]"
_TAG = re.compile(r"<([^ \t\r\n<>/!?]+)((?:" + _WS + r"+[^ \t\r\n<>=/]+" + _WS + r"*=" + _WS
                  + r"""*(?:"[^"<]*"|'[^'<]*'))*)""" + _WS + r"*(/?)>")
_ATTR = re.compile(r"(" + _WS + r"+)([^ \t\r\n<>=/]+)(" + _WS + r"*=" + _WS + r"""*)(?:"([^"<]*)"|'([^'<]*)')""")
_OPEN = re.compile(r"<([^ \t\r\n<>/!?]+)")
_WATCH = ("sym", "Relationship")
_HEX = re.compile(r"^[0-9A-Fa-f]{1,4}$")
_SAFE_SCHEMES = ("http://", "https://", "mailto:")
_XML_PART = re.compile(r"^word/.*\.xml$")
_RELS_PART = re.compile(r"^word/_rels/.*\.rels$")


def _local(name):
    return name.rsplit(":", 1)[-1]


def _attrs(attr_text):
    """[(match, ten cuc bo, gia tri DA giai thuc the)]"""
    out = []
    for m in _ATTR.finditer(attr_text):
        raw = m.group(4) if m.group(4) is not None else m.group(5)
        out.append((m, _local(m.group(2)), html.unescape(raw or "")))
    return out


def _rewrite(tag_m, names, value):
    """The mo voi MOI thuoc tinh co ten cuc bo trong `names` doi gia tri thanh `value`."""
    attr_text = tag_m.group(2)
    new_attrs = _ATTR.sub(lambda m: (m.group(1) + m.group(2) + m.group(3) + '"%s"' % value)
                          if _local(m.group(2)) in names else m.group(0), attr_text)
    return "<" + tag_m.group(1) + new_attrs + (" /" if tag_m.group(3) else "") + ">"


def _clean_tag(m):
    local = _local(m.group(1))
    if local == "sym":
        chars = [v for _m, n, v in _attrs(m.group(2)) if n == "char"]
        if chars and not all(_HEX.match(v.strip()) for v in chars):
            return _rewrite(m, {"char"}, "25A1")
        return m.group(0)
    if local == "Relationship":
        attrs = _attrs(m.group(2))
        if not any(n == "TargetMode" and v.strip().lower() == "external" for _m, n, v in attrs):
            return m.group(0)
        targets = [v for _m, n, v in attrs if n == "Target"]
        if targets and all(v.strip().lower().startswith(_SAFE_SCHEMES) for v in targets):
            return m.group(0)
        return _rewrite(m, {"Target"}, "#")
    return m.group(0)


def _fail_closed(text, part):
    """The sym / Relationship ma bo tach khong doc duoc (sai khuon) -> tu choi xem truoc, khong de lot."""
    for m in _OPEN.finditer(text):
        if _local(m.group(1)) in _WATCH and not _TAG.match(text, m.start()):
            raise ValueError("Mẫu có thẻ %s sai khuôn trong %s - không xem trước được." % (_local(m.group(1)), part))


def sanitize_for_viewer(data):
    """bytes .docx -> bytes .docx da bo ky hieu sai khuon va lien ket ngoai khong phai http(s)/mailto."""
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            raw = src.read(item.filename)
            if (_XML_PART.match(item.filename) and b"sym" in raw) or _RELS_PART.match(item.filename):
                text = raw.decode("utf-8")
                _fail_closed(text, item.filename)
                raw = _TAG.sub(_clean_tag, text).encode("utf-8")
            dst.writestr(item, raw)
    return buf.getvalue()

# Copyright (c) 2026, eCentric and contributors
"""Dien {{placeholder}} vao tep .docx - thuan Python (zipfile + regex), khong thu vien ngoai.

Vi sao khong dung python-docx / ElementTree:
  * Frappe Cloud chi cai dung `pyproject.toml`; them thu vien = them rui ro build.
  * ElementTree doi tien to namespace (w: -> ns0:) khi ghi lai -> Word bao tep hong vi
    `mc:Ignorable` tro toi tien to khong con ton tai.
Nen sua THANG chuoi XML, chi o noi dung <w:t>, giu nguyen moi the khac.

Word hay xe mot placeholder ra nhieu run ("{{ten_" + "creator}}") khi nguoi soan go tung
doan hoac sua chinh ta. Ham nay noi van ban cua ca doan van (<w:p>), tim placeholder tren
chuoi da noi, roi ghi gia tri vao run DAU TIEN ma placeholder cham toi va xoa phan con lai
o cac run sau - dinh dang cua cac run KHONG chua placeholder giu nguyen.

Tra them danh sach placeholder khong co gia tri: mau dung sai ten thi phai bao, khong im lang
de lai "{{...}}" tren hop dong gui di ky.
"""
import io
import re
import zipfile
from xml.sax.saxutils import escape, unescape

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
_PARA = re.compile(r"<w:p[ >].*?</w:p>", re.S)
_TEXT = re.compile(r"(<w:t(?:\s[^>]*)?>)(.*?)(</w:t>)", re.S)
_PARTS = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")


def _fill_paragraph(xml, values, missing):
    runs = list(_TEXT.finditer(xml))
    if not runs:
        return xml
    texts = [unescape(m.group(2)) for m in runs]
    joined = "".join(texts)
    if "{{" not in joined:
        return xml
    matches = list(PLACEHOLDER.finditer(joined))
    if not matches:
        return xml
    starts, pos = [], 0
    for t in texts:
        starts.append(pos)
        pos += len(t)

    def run_at(offset):
        idx = 0
        for i, s in enumerate(starts):
            if s <= offset:
                idx = i
        return idx

    # Phai sang trai de offset cua placeholder truoc khong bi lech.
    for m in reversed(matches):
        key = m.group(1)
        if key not in values:
            missing.add(key)
            continue
        value = "" if values[key] is None else str(values[key])
        a, b = m.start(), m.end()
        first, last = run_at(a), run_at(b - 1)
        for i in range(last, first - 1, -1):
            s = starts[i]
            lo, hi = max(a - s, 0), min(b - s, len(texts[i]))
            replacement = value if i == first else ""
            texts[i] = texts[i][:lo] + replacement + texts[i][hi:]
        # Cap nhat lai moc bat dau sau khi do dai cac run da doi.
        pos = 0
        for i, t in enumerate(texts):
            starts[i] = pos
            pos += len(t)

    original = [unescape(m.group(2)) for m in runs]
    out, last_end = [], 0
    for m, text, before in zip(runs, texts, original):
        if text == before:          # run khong dinh placeholder: giu nguyen tung byte
            continue
        open_tag = m.group(1)
        if text != text.strip() and "xml:space" not in open_tag:
            open_tag = open_tag[:-1] + ' xml:space="preserve">'
        out.append(xml[last_end:m.start()])
        out.append(open_tag + escape(text) + m.group(3))
        last_end = m.end()
    out.append(xml[last_end:])
    return "".join(out)


def fill_xml(xml, values, missing=None):
    missing = set() if missing is None else missing
    return _PARA.sub(lambda m: _fill_paragraph(m.group(0), values, missing), xml), missing


def fill_docx(data, values):
    """bytes .docx -> (bytes .docx da dien, sorted(placeholder khong co gia tri))."""
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    missing = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            raw = src.read(item.filename)
            if _PARTS.match(item.filename):
                xml, _ = fill_xml(raw.decode("utf-8"), values, missing)
                raw = xml.encode("utf-8")
            dst.writestr(item, raw)
    return buf.getvalue(), sorted(missing)


def find_placeholders(data):
    """Moi placeholder trong mau (da noi run) - de kiem mau luc tai len."""
    src = zipfile.ZipFile(io.BytesIO(data))
    found = set()
    for name in src.namelist():
        if not _PARTS.match(name):
            continue
        xml = src.read(name).decode("utf-8")
        for p in _PARA.finditer(xml):
            joined = "".join(unescape(m.group(2)) for m in _TEXT.finditer(p.group(0)))
            found.update(PLACEHOLDER.findall(joined))
    return sorted(found)


def docx_text(data, limit=60000):
    """Van ban thuan cua tep .docx (moi doan mot dong) - de gui AI doc."""
    src = zipfile.ZipFile(io.BytesIO(data))
    xml = src.read("word/document.xml").decode("utf-8")
    lines = []
    for p in _PARA.finditer(xml):
        line = "".join(unescape(m.group(2)) for m in _TEXT.finditer(p.group(0))).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)[:limit]


def is_reportlab_pdf(data):
    """PDF sinh bang ReportLab: 0/6 ky duoc tren SCTS (30/09/2026). Chan truoc khi gui ky."""
    data = bytes(data or b"")
    return b"ReportLab" in data or b"reportlab" in data

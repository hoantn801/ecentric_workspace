# Copyright (c) 2026, eCentric and contributors
"""Dien <<PLACEHOLDER>> vao tep .docx - thuan Python (zipfile + regex), khong thu vien ngoai.

Cu phap <<TEN_IN_HOA>> la cua 18 mau HDDV/BBNT Ke toan dang dung tren tool Google Sheet cu
(anh Hoan chot 12/11/2026 dung lai nguyen ven). Trong XML, "<<" nam o dang "&lt;&lt;" - doc
qua `unescape` truoc khi tim.

Vi sao khong dung python-docx / ElementTree:
  * Frappe Cloud chi cai dung `pyproject.toml`; them thu vien = them rui ro build.
  * ElementTree doi tien to namespace (w: -> ns0:) khi ghi lai -> Word bao tep hong vi
    `mc:Ignorable` tro toi tien to khong con ton tai.
Nen sua THANG chuoi XML, chi o noi dung <w:t>, giu nguyen moi the khac.

Word hay xe mot placeholder ra nhieu run ("<<PERSON_" + "FULL_NAME>>") khi nguoi soan go tung
doan hoac sua chinh ta. Ham nay noi van ban cua ca doan van (<w:p>), tim placeholder tren
chuoi da noi, roi ghi gia tri vao run DAU TIEN ma placeholder cham toi va xoa phan con lai
o cac run sau - dinh dang cua cac run KHONG chua placeholder giu nguyen.

Tra them danh sach placeholder khong co gia tri: mau dung sai ten thi phai bao, khong im lang
de lai "<<...>>" tren hop dong gui di ky.

Dong tuy chon (`drop_if_empty`): gia tri rong -> xoa CA DOAN van (nhu removeBlankConditionalParagraphs_
cua tool cu), de mau co coc khong con dong trong / dau gach treo.
"""
import io
import re
import zipfile
from xml.sax.saxutils import escape
from xml.sax.saxutils import unescape as _unescape

PLACEHOLDER = re.compile(r"<<\s*([A-Z0-9_]+)\s*>>")
# Moi cap <<...>> - de bat ten sai khuon (<<tên>>, <<TEN-CREATOR>>) thay vi bo sot im lang.
ANY_BRACES = re.compile(r"<<([^<>\n]*)>>")
OPEN = "<<"
# Ten kieu cu {{ten}} (truoc 12/11): mau con sot thi BAO, khong im lang gui di ky.
LEGACY = re.compile(r"\{\{([^{}\n]*)\}\}")
# Ky tu dieu khien trong gia tri (go/dan tu Excel) lam document.xml hong.
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Mo doan that su: <w:p> / <w:p w14:paraId=".."> - KHONG khop doan rong tu dong <w:p .../> (khop
# thi tran sang ranh gioi o bang / hang ke tiep, xoa doan tuy chon la xoa luon o - QC 12/11).
_PARA = re.compile(r"<w:p(?:\s[^>]*)?(?<!/)>.*?</w:p>", re.S)
_CELL = re.compile(r"(<w:tc(?:\s[^>]*)?>)(.*?)(</w:tc>)", re.S)
# Khong bat <w:t/> tu dong: [^>]* nuot ca dau "/" se noi sang </w:t> cua run sau va lam hong doan.
_TEXT = re.compile(r"(<w:t(?:\s[^>]*)?(?<!/)>)(.*?)(</w:t>)", re.S)
_TEXT_OR_PARA_END = re.compile(r"</w:p>|(<w:t(?:\s[^>]*)?(?<!/)>)(.*?)(</w:t>)", re.S)
_BREAK = '</w:t><w:br/><w:t xml:space="preserve">'


def unescape(text):
    return _unescape(text, {"&quot;": '"', "&apos;": "'"})


def _bad_names(joined):
    return ["<<%s>>" % m.group(1).strip() for m in ANY_BRACES.finditer(joined)
            if not PLACEHOLDER.fullmatch(m.group(0))] + [
        "{{%s}}" % m.group(1).strip() for m in LEGACY.finditer(joined)]
_PARTS = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")


def _fill_paragraph(xml, values, missing, drop_if_empty=()):
    runs = list(_TEXT.finditer(xml))
    if not runs:
        return xml
    texts = [unescape(m.group(2)) for m in runs]
    joined = "".join(texts)
    if OPEN not in joined:
        if "{{" in joined:
            missing.update(_bad_names(joined))
        return xml
    missing.update(_bad_names(joined))
    matches = list(PLACEHOLDER.finditer(joined))
    if not matches:
        return xml
    if any(m.group(1) in drop_if_empty and not str(values.get(m.group(1)) or "").strip() for m in matches):
        # Xoa ca doan (removeBlankConditionalParagraphs_). Doan chua khung van ban / ngat section
        # thi KHONG xoa (xoa la mat ngat trang hoac cat doi XML) - chi de trong gia tri.
        if "<w:txbxContent" not in xml and "<w:sectPr" not in xml:
            return ""
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
        value = "" if values[key] is None else _CTRL.sub("", str(values[key]))
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
        body = escape(text)
        if "\n" in body:   # dia chi nhieu dong: xuong dong that trong Word, khong de ky tu tho
            body = body.replace("\r\n", "\n").replace("\n", _BREAK)
            if "xml:space" not in open_tag:
                open_tag = open_tag[:-1] + ' xml:space="preserve">'
        out.append(open_tag + body + m.group(3))
        last_end = m.end()
    out.append(xml[last_end:])
    return "".join(out)


def _leftover(xml, values):
    """Placeholder con sot sau khi dien (vd doan van co khung van ban long ben trong: regex doan
    van dung o </w:p> cua khung, phan sau khung khong duoc xu ly). Quet ca phan, bao thieu -
    khong de '<<...>>' lot vao hop dong gui ky. Cung dang ten voi bao thieu thuong (gop trung)."""
    # Moi doan van mot dong ('\n' tai </w:p>): << o doan nay va >> o doan khac khong ghep thanh mot.
    joined = "".join("\n" if m.group(0) == "</w:p>" else unescape(m.group(2))
                     for m in _TEXT_OR_PARA_END.finditer(xml))
    out = set()
    out.update("{{%s}}" % m.group(1).strip() for m in LEGACY.finditer(joined))
    for m in ANY_BRACES.finditer(joined):
        ok = PLACEHOLDER.fullmatch(m.group(0))
        if not ok:
            out.add("<<%s>>" % m.group(1).strip())
        elif ok.group(1) in values:
            out.add("%s (không điền được)" % ok.group(1))
        else:
            out.add(ok.group(1))
    return out


def _keep_cells_valid(xml):
    """Moi o bang (w:tc) phai con it nhat mot doan van - Word bao tep hong neu khong. Xoa dong
    tuy chon la doan duy nhat cua o thi chen lai mot doan rong."""
    def fix(m):
        body = m.group(2)
        if re.search(r"<w:p[\s>/]", body):
            return m.group(0)
        return m.group(1) + body + "<w:p/>" + m.group(3)
    return _CELL.sub(fix, xml) if "<w:tc" in xml else xml


def fill_xml(xml, values, missing=None, drop_if_empty=()):
    missing = set() if missing is None else missing
    drop = frozenset(drop_if_empty or ())
    out = _PARA.sub(lambda m: _fill_paragraph(m.group(0), values, missing, drop), xml)
    return (_keep_cells_valid(out) if drop else out), missing


def fill_docx(data, values, drop_if_empty=()):
    """bytes .docx -> (bytes .docx da dien, sorted(placeholder khong co gia tri))."""
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    missing = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            raw = src.read(item.filename)
            if _PARTS.match(item.filename):
                xml, _ = fill_xml(raw.decode("utf-8"), values, missing, drop_if_empty)
                missing.update(_leftover(xml, values))
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
            found.update(_bad_names(joined))
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

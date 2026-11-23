# Copyright (c) 2026, eCentric and contributors
"""Moc o ky [[KY_BEN_A]] / [[KY_BEN_B]] trong mau Word hop dong + BBNT KOL (chot 18/11/2026 voi chat Ky so,
nhac lai 23/11 - THIETKE_ky_so_hop_dong muc 2e).

Nen tang ky so doc lop chu cua PDF nguoi lap xuat tu Word, thay moc thi dat o ky 180x60pt NGAY TREN
moc, canh trai theo moc (platform/esign/pdf_markers.box_for). Nen moc phai nam:
  * o DAY khoang trong de ky (ngay tren dong ten nguoi ky), de o ky phu len khoang trong;
  * lui vao giua cot cua ben do (o ky rong 180pt) - khong lan sang cot ben kia.
Chu TRANG co 1pt (khong dung thuoc tinh Hidden: Word bo chu an khi xuat PDF).

Hai kieu bo cuc co trong 18 mau Ke toan (do 23/11 tren site):
  * BBNT: bang 2 cot - hang tieu de "ĐẠI DIỆN BÊN A | ĐẠI DIỆN BÊN B" + cac dong trong, hang sau la
    ten nguoi ky (ben A: ten CEO, ben B: <<SIGNATORY_B...>>). -> chen moc DAU moi o cua hang ten.
  * HĐDV: bang tieu de "Thay mặt và đại diện cho ..." 2 cot, roi vai doan trong NGOAI bang, roi MOT doan
    chua ca hai ten (can le bang khoang trang / tab). -> chen mot bang 2 cot khong vien, rong bang
    dung cot cua bang tieu de, ngay TRUOC doan ten.
Neo de tim: doan chua placeholder <<SIGNATORY...>> dau tien SAU tieu de ben B cuoi cung. Khong tim
thay bo cuc quen -> khong sua gi, bao "not_found" (nguoi lap keo o ky tay, nen tang da bao).

THUAN: bytes -> bytes, khong frappe. Chay lai an toan (da co moc -> bo qua).
"""
import io
import re
import zipfile

MARK_A, MARK_B = "[[KY_BEN_A]]", "[[KY_BEN_B]]"
#: O ky cua nen tang rong 180pt = 3600 twip; lui moc de o nam giua cot.
BOX_TWIPS = 3600
#: Bo rong vung chu mac dinh (A4, le 2cm hai ben) khi khong doc duoc luoi cot.
DEFAULT_TEXT_TWIPS = 9638

_HEADER_B = re.compile(r"ĐẠI DIỆN BÊN B|Thay mặt và đại diện cho", re.I)
_SIGNATORY = "&lt;&lt;SIGNATORY"
_PARA = re.compile(r"<w:p[ >].*?</w:p>|<w:p/>", re.S)
_TEXT = re.compile(r"<w:t(?: [^>]*)?>([^<]*)</w:t>")


def _text(xml_fragment):
    return "".join(_TEXT.findall(xml_fragment))


def marker_paragraph(mark, indent_twips):
    """Doan 1pt chu trang chua moc, khong gian cach truoc / sau."""
    return ('<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="40" w:lineRule="exact"/>'
            '<w:ind w:left="%d" w:right="0" w:firstLine="0"/><w:jc w:val="left"/></w:pPr>'
            '<w:r><w:rPr><w:color w:val="FFFFFF"/><w:sz w:val="2"/><w:szCs w:val="2"/></w:rPr>'
            '<w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (max(0, int(indent_twips)), mark))


def _indent_for(width_twips):
    return max(0, (int(width_twips or 0) - BOX_TWIPS) // 2)


def _enclosing(xml, pos, open_re, close_tag):
    """(start, end) cua phan tu bao `pos` gan nhat - co dem long nhau. Khong co -> None."""
    stack = []
    token = re.compile(r"%s|%s" % (open_re, re.escape(close_tag)))
    for m in token.finditer(xml):
        if m.start() >= pos:
            break
        if m.group(0) == close_tag:
            if stack:
                stack.pop()
        else:
            stack.append(m.start())
    if not stack:
        return None
    start = stack[-1]
    depth = 0
    for m in token.finditer(xml, start):
        if m.group(0) == close_tag:
            depth -= 1
            if depth == 0:
                return start, m.end()
        else:
            depth += 1
    return None


def _cells(row_xml):
    """[(start, end)] cua cac o TRUC TIEP trong mot hang (bo qua o cua bang long ben trong)."""
    out, depth, start = [], 0, None
    for m in re.finditer(r"<w:tc>|<w:tc [^>]*>|</w:tc>", row_xml):
        if m.group(0) == "</w:tc>":
            depth -= 1
            if depth == 0 and start is not None:
                out.append((start, m.end()))
                start = None
        else:
            if depth == 0:
                start = m.start()
            depth += 1
    return out


def _cell_width(cell_xml):
    m = re.search(r'<w:tcW [^>]*w:w="(\d+)"[^>]*w:type="dxa"', cell_xml) \
        or re.search(r'<w:tcW [^>]*w:type="dxa"[^>]*w:w="(\d+)"', cell_xml)
    return int(m.group(1)) if m else 0


def _grid_cols(tbl_xml):
    """Cot cua <w:tblGrid> (twip). Bo phan <w:tblGridChange> (Word ghi lai luoi cu khi bat theo
    doi thay doi - 18 mau Ke toan deu co: luoi 2 cot doc ra thanh 4 neu khong bo)."""
    start = tbl_xml.find("<w:tblGrid>")
    if start < 0:
        return []
    seg = tbl_xml[start:]
    cut = [i for i in (seg.find("<w:tblGridChange"), seg.find("</w:tblGrid>")) if i >= 0]
    seg = seg[:min(cut)] if cut else seg
    return [int(w) for w in re.findall(r'<w:gridCol [^>]*w:w="(\d+)"', seg)]


def _cell_insert_at(cell_xml):
    """Vi tri chen doan dau tien trong o: sau <w:tcPr>...</w:tcPr> neu co, khong thi sau the mo."""
    m = re.search(r"</w:tcPr>", cell_xml)
    if m:
        return m.end()
    return re.match(r"<w:tc(?: [^>]*)?>", cell_xml).end()


def _anchor_point(xml):
    """Vi tri (bat dau) doan ten nguoi ky ben B, hoac None."""
    paras = [(m.start(), m.end(), _text(m.group(0))) for m in _PARA.finditer(xml)]
    last_header = None
    for i, (_s, _e, t) in enumerate(paras):
        if _HEADER_B.search(t):
            last_header = i
    if last_header is None:
        return None
    for s, e, t in paras[last_header + 1:]:
        if _SIGNATORY in t:
            return s
    return None


def _in_cell(xml, pos):
    return _enclosing(xml, pos, r"<w:tc>|<w:tc [^>]*>", "</w:tc>")


def _insert_in_row(xml, pos):
    """BBNT: doan ten nam trong o -> chen moc dau o ben A (o dau) va o ben B (o chua doan ten)."""
    row = _enclosing(xml, pos, r"<w:tr>|<w:tr [^>]*>", "</w:tr>")
    if not row:
        return None
    r_start, r_end = row
    row_xml = xml[r_start:r_end]
    cells = _cells(row_xml)
    if len(cells) < 2:
        return None
    b_idx = next((i for i, (s, e) in enumerate(cells) if s <= pos - r_start < e), None)
    if b_idx is None or b_idx == 0:
        return None
    tbl = _enclosing(xml, pos, r"<w:tbl>|<w:tbl [^>]*>", "</w:tbl>")
    grid = _grid_cols(xml[tbl[0]:tbl[1]]) if tbl else []
    new_row = row_xml
    # Chen tu phai sang trai de vi tri o ben trai khong doi.
    for idx, mark in ((b_idx, MARK_B), (0, MARK_A)):
        s, e = cells[idx]
        cell = row_xml[s:e]
        # Mau BBNT khong ghi tcW cho tung o: lay be rong cot tu luoi bang (khong gop o).
        width = _cell_width(cell) or (grid[idx] if len(grid) == len(cells) else 0)
        at = s + _cell_insert_at(cell)
        new_row = new_row[:at] + marker_paragraph(mark, _indent_for(width)) + new_row[at:]
    return xml[:r_start] + new_row + xml[r_end:], "row"


def _grid_before(xml, pos):
    """Luoi cot (twip) cua bang gan nhat dung TRUOC pos + tblInd / jc cua bang do."""
    end = xml.rfind("</w:tbl>", 0, pos)
    if end < 0:
        return None, "", ""
    tbl = _enclosing(xml, end, r"<w:tbl>|<w:tbl [^>]*>", "</w:tbl>")
    if not tbl:
        return None, "", ""
    tbl_xml = xml[tbl[0]:tbl[1]]
    cols = _grid_cols(tbl_xml.split("<w:tr", 1)[0])
    pr = re.search(r"<w:tblPr>.*?</w:tblPr>", tbl_xml, re.S)
    pr = pr.group(0) if pr else ""
    ind = re.search(r"<w:tblInd [^>]*/>", pr)
    jc = re.search(r"<w:jc [^>]*/>", pr)
    return cols, (ind.group(0) if ind else ""), (jc.group(0) if jc else "")


def _marker_table(widths, tbl_ind="", tbl_jc=""):
    none = "".join('<w:%s w:val="nil"/>' % b for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
    cells = "".join('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/></w:tcPr>%s</w:tc>'
                    % (w, marker_paragraph(mark, _indent_for(w)))
                    for w, mark in zip(widths, (MARK_A, MARK_B)))
    return ('<w:tbl><w:tblPr><w:tblW w:w="%d" w:type="dxa"/>%s%s<w:tblBorders>%s</w:tblBorders>'
            '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:left w:w="0" w:type="dxa"/>'
            '<w:right w:w="0" w:type="dxa"/></w:tblCellMar><w:tblLook w:val="0000"/></w:tblPr>'
            '<w:tblGrid>%s</w:tblGrid><w:tr>%s</w:tr></w:tbl>'
            % (sum(widths), tbl_ind, tbl_jc, none,
               "".join('<w:gridCol w:w="%d"/>' % w for w in widths), cells))


def _insert_table_before(xml, pos):
    """HĐDV: doan ten nam ngoai bang -> chen bang 2 cot (theo luoi bang tieu de) ngay truoc no."""
    cols, ind, jc = _grid_before(xml, pos)
    if cols and len(cols) >= 2:
        total = sum(cols)
        left = cols[0] if len(cols) == 2 else total // 2
        widths = (left, total - left)
    else:
        widths = (DEFAULT_TEXT_TWIPS // 2, DEFAULT_TEXT_TWIPS - DEFAULT_TEXT_TWIPS // 2)
        ind = jc = ""
    return xml[:pos] + _marker_table(widths, ind, jc) + xml[pos:], "table"


def insert_markers(xml):
    """document.xml -> (xml moi, cach chen) | (None, ly do)."""
    if "KY_BEN_A" in xml or "KY_BEN_B" in xml:
        return None, "already"
    pos = _anchor_point(xml)
    if pos is None:
        return None, "not_found"
    if _in_cell(xml, pos):
        res = _insert_in_row(xml, pos)
        return res if res else (None, "row_layout_unknown")
    return _insert_table_before(xml, pos)


def add_markers(data):
    """bytes .docx -> (bytes moi hoac nguyen ban, {"status": added|already|not_found|..., "how"}).
    Giu nguyen thu tu va kieu nen tung muc trong goi zip."""
    src = zipfile.ZipFile(io.BytesIO(data))
    xml = src.read("word/document.xml").decode("utf-8")
    new_xml, how = insert_markers(xml)
    if new_xml is None:
        return data, {"status": how}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as dst:
        for item in src.infolist():
            raw = new_xml.encode("utf-8") if item.filename == "word/document.xml" else src.read(item.filename)
            dst.writestr(item, raw, compress_type=item.compress_type)
    return buf.getvalue(), {"status": "added", "how": how}


def has_markers(data):
    try:
        xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    except Exception:
        return False
    return MARK_A in _text(xml) and MARK_B in _text(xml)

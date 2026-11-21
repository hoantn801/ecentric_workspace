# Copyright (c) 2026, eCentric and contributors
"""Doc lop chu cua PDF: tim MOC dat o ky + chu tung trang (chot 18/11/2026, THIETKE_ky_so_hop_dong
muc 2e). KHONG import frappe - thuan tinh toan, test duoc doc lap.

Mau EC (HD / BBNT KOL) dat moc `[[KY_BEN_A]]` (eCentric) va `[[KY_BEN_B]]` (doi tac) bang chu
TRANG co 1pt (KHONG dung thuoc tinh Hidden cua Word - Word bo chu an khi xuat PDF). Nguoi lap tai
ban PDF xuat tu Word; moc van con trong lop chu.

Cach doc:
  * pypdf `extract_text(visitor_text=...)` -> tung MANH chu kem toa do (ma tran tm x cm);
  * gom manh theo trang + dong (lech y <= LINE_TOL pt), xep theo x, NOI lai roi moi so khop -
    pypdf hay cat moc thanh nhieu manh (`[[KY_` + `BEN_A]]`);
  * moc nam tren HAI dong khac nhau -> coi nhu khong co moc.
  * Toa do tra ve theo he CHUAN cua coords.py: goc TREN-TRAI cua trang (cropbox), don vi point,
    page_index tu 1. Trang XOAY (Rotate khac 0): bo moc tren trang do, bao ly do (khong doan).

Tra ve `analyze(content) -> {"ok", "pages_text", "text_chars", "has_text_layer", "markers",
"skipped"}`; markers = [{"name": "KY_BEN_A", "page_index", "x", "y", "font_size"}] voi (x, y) la
goc trai, DUONG CHAN CHU cua moc (y tinh tu tren xuong).
"""
import io
import re

LINE_TOL = 2.0            # pt - cung mot dong
MIN_TEXT_CHARS = 20       # it hon -> coi nhu khong co lop chu (scan / in ra anh)
MARKER_RE = re.compile(r"\[\[(KY_BEN_[AB])\]\]")   # so tren chuoi DA BO khoang trang


def _reader(content):
    try:
        from pypdf import PdfReader
    except Exception:                                   # bench cu
        from PyPDF2 import PdfReader
    return PdfReader(io.BytesIO(content))


def _matmul(m1, m2):
    """Tich hai ma tran PDF [a b c d e f] (m1 x m2)."""
    a1, b1, c1, d1, e1, f1 = [float(v) for v in m1]
    a2, b2, c2, d2, e2, f2 = [float(v) for v in m2]
    return [a1 * a2 + b1 * c2, a1 * b2 + b1 * d2, c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
            e1 * a2 + f1 * c2 + e2, e1 * b2 + f1 * d2 + f2]


def _mul(tm, cm):
    """Diem goc cua ma tran chu (tm) trong khong gian trang (nhan voi cm)."""
    m = _matmul(tm, cm)
    return m[4], m[5]


def _lines(frags):
    """Gom manh [(x, y, text, size)] thanh dong: [(y, [(x, text, size)...])] tu tren xuong."""
    lines = []
    for x, y, t, size in sorted(frags, key=lambda f: (-f[1], f[0])):
        for ln in lines:
            if abs(ln[0] - y) <= LINE_TOL:
                ln[1].append((x, t, size))
                break
        else:
            lines.append([y, [(x, t, size)]])
    for ln in lines:
        ln[1].sort(key=lambda p: p[0])
    return lines


def _find_markers(lines):
    """Moc tren tung dong da noi. Tra [(name, x_pdf, y_pdf, size, reliable)].

    So khop tren chuoi DA BO moi khoang trang (pypdf chen dau cach o khe kerning / nhay vi tri:
    `[ [KY_BEN_A]]`, `[[KY_ BEN_A]]` - QC 22/11), giu ban do chi so ve manh goc.
    `reliable` False khi manh chua moc co CUNG x voi manh khac tren dong: pypdf khong cong do rong
    chu giua cac Tj lien tiep trong mot khoi BT, nen x cua manh sau bi lui ve dau khoi."""
    out = []
    for y, parts in lines:
        compact, owner = [], []                 # ky tu khong khoang trang -> chi so manh
        for i, (x, t, size) in enumerate(parts):
            for ch in t:
                if not ch.isspace():
                    compact.append(ch)
                    owner.append(i)
        text = "".join(compact)
        for m in MARKER_RE.finditer(text):
            i = owner[m.start()]
            x, _t, size = parts[i]
            # Moc bat dau giua manh: uoc luong lech theo so ky tu dung truoc trong manh do.
            before = sum(1 for k in range(m.start()) if owner[k] == i)
            offset = before * float(size or 0) * 0.5
            mine = {owner[k] for k in range(m.start(), m.end())}
            # Manh chu KHAC (khong thuoc moc) dung TRUOC moc ma cung x -> x khong tin duoc.
            clash = any(j not in mine and j < i and abs(float(parts[j][0]) - float(x)) < 0.01
                        for j in range(len(parts)))
            # Moc bat dau GIUA manh (cung manh voi chu khac): vi tri uoc luong khong tin duoc.
            out.append((m.group(1), float(x) + offset, float(y), float(size or 0),
                        not clash and before == 0))
    return out


def analyze(content):
    """Doc mot PDF (bytes). Khong nem loi: PDF hong -> ok False."""
    try:
        reader = _reader(bytes(content or b""))
        pages = list(reader.pages)
    except Exception as e:                              # pragma: no cover - PDF hong
        return {"ok": False, "reason": "pdf_unreadable:%s" % type(e).__name__,
                "pages_text": [], "text_chars": 0, "has_text_layer": False,
                "markers": [], "skipped": []}
    pages_text, markers, skipped, chars = [], [], [], 0
    for idx, pg in enumerate(pages, start=1):
        frags = []

        def visit(text, cm, tm, font_dict, font_size, _f=frags):
            if text and text.strip("\n"):
                mm = _matmul(tm, cm)
                if abs(mm[1]) > 1e-3 or abs(mm[2]) > 1e-3:
                    return                    # chu XOAY / nghieng: khong dung lam moc (QC 22/11)
                # co chu THAT = co khai bao x ti le doc cua ma tran (QC 22/11)
                eff = float(font_size or 0) * abs(mm[3])
                _f.append((mm[4], mm[5], text.replace("\n", ""), eff or float(font_size or 0)))
        try:
            plain = pg.extract_text(visitor_text=visit) or ""
        except Exception:
            plain = ""
        pages_text.append(plain)
        # Khong tinh chu cua moc: ban scan + moc khong duoc coi la "co lop chu" (QC 22/11).
        chars += len(MARKER_RE.sub("", "".join(plain.split())))
        found = _find_markers(_lines(frags))
        if not found:
            continue
        try:
            rot = int(pg.get("/Rotate", 0) or 0) % 360
        except Exception:
            rot = 0
        if rot:
            skipped.extend({"name": f[0], "page_index": idx, "reason": "rotated_page:%d" % rot}
                           for f in found)
            continue
        box = getattr(pg, "cropbox", None) or pg.mediabox
        left, top = float(box.left), float(box.top)
        for name, x, y, size, reliable in found:
            if not reliable:
                skipped.append({"name": name, "page_index": idx,
                                "reason": "position_unreliable"})
                continue
            markers.append({"name": name, "page_index": idx, "x": round(x - left, 2),
                            "y": round(top - y, 2), "font_size": size,
                            "page_width": float(box.width), "page_height": float(box.height)})
    return {"ok": True, "pages_text": pages_text, "text_chars": chars,
            "has_text_layer": chars >= MIN_TEXT_CHARS, "markers": markers, "skipped": skipped}


#: O ky mac dinh (point) va khoang ho phia tren moc.
BOX_W, BOX_H, GAP = 180.0, 60.0, 2.0


def box_for(marker):
    """O ky 180x60pt NGAY TREN moc (canh trai theo moc), ep vao trong trang. He chuan coords."""
    pw, ph = float(marker["page_width"]), float(marker["page_height"])
    w, h = min(BOX_W, pw), min(BOX_H, ph)
    x = min(max(0.0, float(marker["x"])), pw - w)
    y = float(marker["y"]) - float(marker.get("font_size") or 0) - GAP - h
    y = min(max(0.0, y), ph - h)
    return {"page_index": marker["page_index"], "x": round(x, 2), "y": round(y, 2),
            "width": w, "height": h}

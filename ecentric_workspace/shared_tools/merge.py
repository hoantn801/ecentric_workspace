# Copyright (c) 2026, eCentric and contributors
"""Gop cac phan CSV cua mot lan xuat nhieu trang thanh MOT file Excel - ham thuan (khong frappe).

Moi phan co cung dong tieu de (extension giu nguyen bo cot tu phan 1). Phan nao lech tieu de thi van
gop, cot doi theo tieu de phan 1 (cot thieu de trong, cot thua bo) - khong lam hong ca file.
"""
import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

MAX_ROWS = 1_000_000  # Excel toi da 1.048.576 dong


def _rows(content):
    raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    text = raw.decode("utf-8-sig", errors="replace")
    return list(csv.reader(io.StringIO(text)))


def merge(parts):
    """parts: [(so phan, noi dung csv)] -> (tieu de, cac dong) theo thu tu phan."""
    header, out = None, []
    for _, content in sorted(parts, key=lambda p: p[0]):
        rows = _rows(content)
        if not rows:
            continue
        h, body = rows[0], rows[1:]
        if header is None:
            header = h
        if h != header:
            idx = {name: i for i, name in enumerate(h)}
            body = [[(r[idx[c]] if c in idx and idx[c] < len(r) else "") for c in header] for r in body]
        out.extend(body)
        if len(out) > MAX_ROWS:
            raise ValueError("Quá %d dòng, Excel không chứa nổi. Tải từng phần CSV." % MAX_ROWS)
    return header or [], out


def to_xlsx(header, rows, sheet="Kalodata"):
    wb = Workbook(write_only=False)
    ws = wb.active
    ws.title = sheet[:31]
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append(r)
    ws.freeze_panes = "A2"
    for i, name in enumerate(header, start=1):
        sample = [len(str(name))] + [len(str(r[i - 1])) for r in rows[:200] if i - 1 < len(r)]
        ws.column_dimensions[get_column_letter(i)].width = min(60, max(10, max(sample) + 2))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

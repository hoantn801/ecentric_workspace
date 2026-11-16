# Copyright (c) 2026, eCentric and contributors
"""Tệp đi từ người dùng vào ERP cho Claude dùng.

VÌ SAO CẦN TRANG TẢI LÊN RIÊNG. MCP không chở được tệp: tệp người dùng thả vào khung chat Claude
nằm ở phía Claude, công cụ chỉ nhận được chữ. Base64 cả hợp đồng vào tham số thì tốn hàng trăm
nghìn token mỗi tệp. Nên Claude đưa link /claude_tep, người dùng thả tệp vào đó (đăng nhập ERP như
thường), tệp thành File riêng tư của CHÍNH họ - y như ô "Tệp đính kèm" trên form tạo phiếu
(upload_file is_private=1, không kèm doctype). Sau đó Claude đọc chữ trong tệp và gắn vào phiếu.

QUYỀN ĐỌC TỆP: dùng lại ai_attachments.may_read - chỉ tệp mình tải lên, hoặc tệp đang gắn vào hồ sơ
mình đọc được. Không có cửa thứ ba (đọc docstring của module đó).
"""
import io
import re
import zipfile

import frappe
from frappe.utils import add_to_date, now_datetime

from ecentric_workspace.claude_mcp.protocol import ToolError

UPLOAD_PATH = "/claude_tep"
TEXT_CAP = 40000
PDF_PAGE_CAP = 40


def _may_read(row):
    from ecentric_workspace.approval_center.shared.integrations import ai_attachments
    return ai_attachments.may_read(row)


def resolve_file(ref):
    """`ref` = tên File, file_url hoặc tên tệp vừa tải lên -> dict File đọc được, hoặc ToolError."""
    ref = str(ref or "").strip()
    if not ref:
        raise ToolError("Thiếu tệp.")
    fields = ["name", "file_name", "file_url", "is_private", "owner", "attached_to_doctype",
              "attached_to_name", "file_size", "creation"]
    rows = []
    if frappe.db.exists("File", ref):
        rows = frappe.get_all("File", filters={"name": ref}, fields=fields, limit_page_length=1)
    if not rows and ref.startswith(("/files/", "/private/files/")):
        rows = frappe.get_all("File", filters={"file_url": ref}, fields=fields,
                              order_by="creation desc", limit_page_length=20)
    if not rows:
        rows = frappe.get_all("File", filters={"file_name": ref, "owner": frappe.session.user},
                              fields=fields, order_by="creation desc", limit_page_length=5)
    for r in rows:
        if _may_read(r):
            return r
    raise ToolError("Không tìm thấy tệp '%s' (hoặc bạn không có quyền đọc). Dùng list_my_uploads để xem tên tệp." % ref)


def upload_link():
    from frappe.utils import get_url
    return get_url(UPLOAD_PATH)


def list_my_uploads(hours=24, include_attached=False):
    hours = max(1, min(int(hours or 24), 24 * 14))
    filters = {"owner": frappe.session.user, "is_folder": 0,
               "creation": [">=", add_to_date(now_datetime(), hours=-hours)]}
    rows = frappe.get_all("File", filters=filters,
                          fields=["name", "file_name", "file_url", "file_size", "creation",
                                  "attached_to_doctype", "attached_to_name", "is_private"],
                          order_by="creation desc", limit_page_length=100)
    out = []
    for r in rows:
        attached = bool(r.get("attached_to_doctype") and r.get("attached_to_name"))
        if attached and not include_attached:
            continue
        out.append({k: v for k, v in {
            "file": r["name"], "file_name": r.get("file_name"),
            "size_kb": int((r.get("file_size") or 0) / 1024) or None,
            "uploaded_at": str(r.get("creation"))[:16],
            "attached_to": ("%s/%s" % (r["attached_to_doctype"], r["attached_to_name"])) if attached else None,
        }.items() if v not in (None, "")})
    return {"upload_link": upload_link(), "files": out, "hours": hours,
            "note": ("Chưa có tệp nào. Gửi link upload_link cho người dùng, nhờ họ thả tệp vào đó rồi gọi lại."
                     if not out else "Tệp chưa gắn vào phiếu nào (tải lên trong %s giờ qua)." % hours)}


def file_bytes(row):
    from ecentric_workspace.approval_center.shared.integrations import ai_attachments
    return ai_attachments._content_bytes(row["name"])


def read_file(file, max_chars=TEXT_CAP):
    row = resolve_file(file)
    name = (row.get("file_name") or row.get("file_url") or "").lower()
    data = file_bytes(row)
    cap = max(1000, min(int(max_chars or TEXT_CAP), TEXT_CAP))
    out = {"file": row["name"], "file_name": row.get("file_name"), "size_kb": int(len(data) / 1024)}
    try:
        if data[:4] == b"%PDF" or name.endswith(".pdf"):
            text, pages = pdf_text(data)
            out["pages"] = pages
            if len(re.sub(r"\s+", "", text)) < 40:
                out["scanned"] = True
                out["hint"] = ("PDF dạng ảnh scan, không có lớp chữ. Nhờ người dùng thả CHÍNH tệp này vào khung "
                               "chat để Claude đọc bằng mắt; tệp trên ERP vẫn dùng để gắn vào phiếu.")
        elif name.endswith(".docx"):
            text = docx_text(data)
        elif name.endswith((".xlsx", ".xlsm")):
            text = xlsx_text(data)
        elif name.endswith((".txt", ".csv", ".md")):
            text = data.decode("utf-8", errors="replace")
        else:
            out["hint"] = ("Loại tệp này không đọc chữ được (ảnh, .doc, .xls...). Nhờ người dùng thả tệp vào khung "
                           "chat để Claude xem; hoặc xuất ra PDF/DOCX/XLSX.")
            text = ""
    except Exception as exc:
        raise ToolError("Không đọc được tệp %s: %s" % (row.get("file_name"), str(exc)[:200])) from None
    out["truncated"] = len(text) > cap
    out["text"] = text[:cap]
    return out


def pdf_text(data):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for i, page in enumerate(reader.pages[:PDF_PAGE_CAP]):
        parts.append("--- Trang %d ---\n%s" % (i + 1, (page.extract_text() or "").strip()))
    return "\n\n".join(parts), len(reader.pages)


def docx_text(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    import html
    return html.unescape(re.sub(r"<[^>]+>", "", xml)).strip()


def xlsx_text(data, max_rows=300):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts = []
    for ws in wb.worksheets[:5]:
        parts.append("--- Sheet %s ---" % ws.title)
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= max_rows:
                parts.append("…")
                break
            if any(v not in (None, "") for v in row):
                parts.append("\t".join("" if v is None else str(v) for v in row))
    return "\n".join(parts)


# ------------------------------------------------------------------ vị trí chữ trong PDF
#: Dòng chữ hay đứng ngay trên chỗ ký. So khớp KHÔNG DẤU (pypdf hay làm rơi dấu tiếng Việt).
SIGN_HINTS = ("dai dien", "nguoi de nghi", "nguoi lap", "nguoi nhan", "giam doc", "ke toan",
              "ky, ghi ro", "ky ghi ro", "ky va ghi ro", "ky ten", "xac nhan", "ben a", "ben b",
              "truong phong", "phe duyet", "nguoi duyet", "thu truong", "chu tich", "tong giam doc")


def text_positions(data):
    """-> [{page, text, x, top, page_w, page_h}] mỗi đoạn chữ, toạ độ GỐC TRÊN-TRÁI theo điểm (pt),
    tính trên cropbox - đúng hệ toạ độ mà esign/coords.py + validate_placement_geometry dùng."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    out = []
    for pi, page in enumerate(reader.pages[:PDF_PAGE_CAP]):
        if int(page.get("/Rotate") or 0) % 360:
            continue  # trang xoay: không tự đặt, để người dùng kéo
        box = getattr(page, "cropbox", None) or page.mediabox
        left, bottom = float(box.left), float(box.bottom)
        w, h = float(box.width), float(box.height)
        chunks = []

        def visit(text, cm, tm, _font, _size, _chunks=chunks):
            t = (text or "").strip()
            if not t:
                return
            # toạ độ người dùng = tm x cm
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            _chunks.append((t, x, y))

        try:
            page.extract_text(visitor_text=visit)
        except Exception:
            continue
        for t, x, y in chunks:
            top = (bottom + h) - y
            if 0 <= x - left <= w and 0 <= top <= h:
                out.append({"page": pi + 1, "text": t, "x": round(x - left, 1), "top": round(top, 1),
                            "page_w": round(w, 1), "page_h": round(h, 1)})
    return out


def signature_anchors(data, limit=40):
    from ecentric_workspace.claude_mcp.tools import fold
    hits = []
    for c in text_positions(data):
        f = fold(c["text"])
        if any(k in f for k in SIGN_HINTS) and len(f) <= 120:
            hits.append(c)
    return hits[:limit]


def box_under(anchor, width=150.0, height=60.0, gap=4.0):
    """Ô ký ngay dưới dòng chữ mốc, căn giữa theo đầu dòng, kẹp trong trang."""
    w, h = anchor["page_w"], anchor["page_h"]
    x = max(4.0, min(anchor["x"] - 10.0, w - width - 4.0))
    y = max(4.0, min(anchor["top"] + gap, h - height - 4.0))
    return {"page_index": anchor["page"], "x": round(x, 1), "y": round(y, 1),
            "width": float(width), "height": float(height)}

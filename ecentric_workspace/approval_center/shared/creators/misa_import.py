# Copyright (c) 2026, eCentric and contributors
"""Nhap ma khach hang MISA hang loat tu tep (PO 24/11/2026, tab "Creator (mã MISA)" form 27).

Luong: Ke toan bam "Xuat CSV" (co cot khoa `ma_erp` + cot `ma_misa` de trong) -> dien ma -> "Nhap file"
-> preview() doc tep + kiem TUNG dong, KHONG ghi -> "Xac nhan N dong hop le" -> apply() kiem LAI toan bo
phia server roi ghi tung dong qua DUNG CreatorService.set_misa_code (quyen + luat + ghi vet nhu nut Luu
tung dong). Khong tin client: apply chi nhan cap (ma_erp, ma_misa), tu kiem lai moi thu.

Khong goi frappe: doc tep bang csv / openpyxl, moi doc-ghi DB di qua service -> repository.
"""
import base64
import binascii
import csv
import io
import unicodedata

from ecentric_workspace.approval_center.shared.creators.import_service import header_key
from ecentric_workspace.approval_center.shared.creators.service import (
    CreatorError, CreatorService, MisaCodeError)

MAX_ROWS = 500
MAX_BYTES = 2 * 1024 * 1024
MAX_COLS = 60
KEY_ALIASES = ("ma_erp", "name", "ma_creator", "creator_id")
NAME_ALIASES = ("ten", "supplier_name", "ten_creator")   # chi de hien, khong dung de khop
CODE_ALIASES = ("ma_misa", "misa_code", "ma_khach_hang_misa", "ma_khach_hang", "ma_kh", "ec_cr_misa_code")
STATUS_LABELS = {
    "khop": "Khớp",
    "ma_trong": "Mã trống",
    "sai_dinh_dang": "Mã sai định dạng",
    "khong_tim_thay": "Không tìm thấy creator",
    "creator_lap": "Creator lặp trong file",
    "trung_trong_file": "Mã trùng trong file",
    "trung_creator_khac": "Mã đã gán cho creator khác",
    "da_co_ma": "Creator đã có mã (khác)",
    "da_co_cung_ma": "Đã có đúng mã này",
    "da_luu": "Đã lưu",
    "loi": "Lỗi khi lưu",
}
#: Khong phai loi: dong de trong ma (chua tao tren MISA) / creator da co dung ma (chay lai cung tep).
SKIP_STATUSES = ("ma_trong", "da_co_cung_ma")
_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


# ---- doc tep -----------------------------------------------------------------------------------
def decode_content(content):
    """Noi dung tep client gui: base64 (co the kem tien to data URL) -> bytes."""
    text = str(content or "")
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    if not text.strip():
        raise CreatorError("Tệp trống.")
    if len(text) > MAX_BYTES * 4 // 3 + 8:
        raise CreatorError("Tệp quá lớn (tối đa 2 MB).")
    try:
        return base64.b64decode(text, validate=False)
    except (binascii.Error, ValueError):
        raise CreatorError("Không đọc được nội dung tệp.")


def _cell(value):
    """Gia tri o -> chuoi sach. Bo dau ' chong cong thuc ma nut Xuat CSV them; so nguyen Excel -> '123'."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if hasattr(value, "isoformat"):
        value = value.isoformat()
    text = unicodedata.normalize("NFC", str(value).replace(" ", " ").replace("﻿", "")).strip()
    if len(text) > 1 and text[0] == "'" and text[1] in _FORMULA_PREFIX:
        text = text[1:]
    return text


def _decode_text(raw):
    for enc in ("utf-8-sig", "cp1258"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_csv(raw):
    text = _decode_text(raw)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    return [row[:MAX_COLS] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _read_xlsx(raw):
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise CreatorError("Máy chủ chưa đọc được tệp .xlsx - lưu tệp dạng CSV UTF-8 rồi nhập lại.")
    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception:
        raise CreatorError("Không đọc được tệp Excel (.xlsx). Mở lại bằng Excel rồi lưu, hoặc lưu dạng CSV UTF-8.")
    try:
        ws = wb.worksheets[0]
        out = []
        for row in ws.iter_rows(values_only=True, max_col=MAX_COLS):
            out.append(list(row))
            if len(out) > MAX_ROWS + 50:   # du dong trong / tieu de; con lai bao qua gioi han o duoi
                break
        return out
    finally:
        wb.close()


def read_table(filename, raw):
    """bytes cua tep -> danh sach dong (list gia tri tho). CSV hoac .xlsx."""
    if len(raw) > MAX_BYTES:
        raise CreatorError("Tệp quá lớn (tối đa 2 MB).")
    name = str(filename or "").lower()
    if name.endswith(".xls"):
        raise CreatorError("Tệp .xls (Excel cũ) chưa hỗ trợ: lưu lại dạng .xlsx hoặc CSV UTF-8.")
    if name.endswith((".xlsx", ".xlsm")) or raw[:2] == b"PK":
        return _read_xlsx(raw)
    return _read_csv(raw)


def rows_from_table(table):
    """Bang tho -> [{"line", "name", "code"}]. Dong tieu de = dong khong trong dau tien."""
    cleaned = [[_cell(v) for v in (row or [])] for row in table]
    start = next((i for i, row in enumerate(cleaned) if any(row)), None)
    if start is None:
        raise CreatorError("Tệp không có dữ liệu.")
    head = [header_key(h) for h in cleaned[start]]

    def col(aliases):
        for alias in aliases:
            if alias in head:
                return head.index(alias)
        return None

    key_i, code_i, name_i = col(KEY_ALIASES), col(CODE_ALIASES), col(NAME_ALIASES)
    missing = [label for i, label in ((key_i, "ma_erp (mã creator trên ERP)"), (code_i, "ma_misa")) if i is None]
    if missing:
        raise CreatorError("Tệp thiếu cột %s. Dùng tệp từ nút \"Xuất CSV\" và điền mã vào cột ma_misa."
                           % ", ".join(missing))
    items = []
    for offset, row in enumerate(cleaned[start + 1:], start=start + 2):   # so dong nhu Excel hien
        if not any(row):
            continue
        get = (lambda i: row[i] if i is not None and i < len(row) else "")
        items.append({"line": offset, "name": get(key_i), "code": get(code_i), "ten": get(name_i)})
        if len(items) > MAX_ROWS:
            raise CreatorError("Tối đa %d dòng mỗi lần nhập - chia tệp thành nhiều lần." % MAX_ROWS)
    if not items:
        raise CreatorError("Tệp chỉ có dòng tiêu đề, chưa có dòng creator nào.")
    return items


# ---- kiem ---------------------------------------------------------------------------------------
def _norm_items(items):
    out = []
    for i, raw in enumerate(items or [], start=1):
        if not isinstance(raw, dict):
            raise CreatorError("Dòng %d không hợp lệ." % i)
        try:
            line = int(raw.get("line") or i)
        except (TypeError, ValueError):
            line = i
        out.append({"line": line, "name": _cell(raw.get("name")), "code": _cell(raw.get("code")),
                    "ten": _cell(raw.get("ten"))[:140]})
    if len(out) > MAX_ROWS:
        raise CreatorError("Tối đa %d dòng mỗi lần nhập - chia tệp thành nhiều lần." % MAX_ROWS)
    return out


def classify(service, items):
    """Gan trang thai cho tung dong. Luat gan ma nam o service.check_misa_code; o day chi them luat
    CA TEP (mot creator / mot ma xuat hien nhieu dong)."""
    rows = _norm_items(items)
    filled = [r for r in rows if r["code"]]
    by_name, by_code = {}, {}
    for r in filled:
        if r["name"]:
            by_name[r["name"]] = by_name.get(r["name"], 0) + 1
        by_code[r["code"].casefold()] = by_code.get(r["code"].casefold(), 0) + 1
    out = []
    for r in rows:
        item = {"line": r["line"], "name": r["name"], "code": r["code"], "supplier_name": ""}
        try:
            if not r["name"]:
                raise MisaCodeError("khong_tim_thay", "Dòng thiếu mã ERP (cột ma_erp).")
            row = None
            if r["code"]:
                row = service.repo.get(r["name"])
                item["supplier_name"] = (row or {}).get("supplier_name") or ""
                if row and by_name.get(r["name"], 0) > 1:
                    raise MisaCodeError("creator_lap", "Creator này có %d dòng có mã trong tệp - giữ một dòng."
                                        % by_name[r["name"]])
                if by_code.get(r["code"].casefold(), 0) > 1 and not service.repo.misa_owner(r["code"], ""):
                    raise MisaCodeError("trung_trong_file", "Mã %s xuất hiện %d dòng trong tệp."
                                        % (r["code"], by_code[r["code"].casefold()]))
            service.check_misa_code(r["name"], r["code"], overwrite=False, row=row)
            item.update(status="khop", message="")
        except MisaCodeError as e:
            item.update(status=e.status, message=str(e))
        if not item["supplier_name"] and item["status"] == "khong_tim_thay" and "?" in r["name"]:
            item["message"] += " Tên có dấu '?' - tệp CSV bị lưu mất dấu: lưu lại dạng CSV UTF-8 hoặc .xlsx."
        item["supplier_name"] = item["supplier_name"] or r["ten"]
        item["label"] = STATUS_LABELS.get(item["status"], item["status"])
        out.append(item)
    return out


def _counts(rows):
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def preview(user, filename, content, service=None):
    """Doc tep + kiem tung dong. KHONG ghi gi. Chi EC Finance / System Manager."""
    service = service or CreatorService()
    service.require_finance(user)
    items = rows_from_table(read_table(filename, decode_content(content)))
    rows = classify(service, items)
    counts = _counts(rows)
    return {"filename": str(filename or "")[:120], "total": len(rows), "valid": counts.get("khop", 0),
            "counts": counts, "labels": STATUS_LABELS, "max_rows": MAX_ROWS, "rows": rows}


def apply(user, items, filename=None, service=None):
    """Ap dung hang loat. Kiem LAI moi dong o server (khong tin trang thai client gui), dong Khop thi ghi
    qua service.set_misa_code (kiem quyen + luat lan nua ngay truoc khi ghi + ghi vet). Dong loi khong lam
    hong dong khac; ket qua tra tung dong + ly do."""
    service = service or CreatorService()
    service.require_finance(user)
    if not isinstance(items, list):
        raise CreatorError("Danh sách dòng không hợp lệ.")
    if not items:
        raise CreatorError("Không có dòng nào để lưu.")
    rows = classify(service, items)
    source = str(filename or "").strip()[:120]
    for r in rows:
        if r["status"] != "khop":
            continue
        note = "%s gán mã khách hàng MISA %s (nhập hàng loạt%s)." % (
            user, r["code"], (" từ tệp " + source) if source else "")
        try:
            service.set_misa_code(user, r["name"], r["code"], note=note, overwrite=False)
            r.update(status="da_luu", message="")
        except MisaCodeError as e:
            r.update(status=e.status, message=str(e))
        except CreatorError as e:
            r.update(status="loi", message=str(e))
        r["label"] = STATUS_LABELS.get(r["status"], r["status"])
    counts = _counts(rows)
    saved = counts.get("da_luu", 0)
    skipped = sum(counts.get(s, 0) for s in SKIP_STATUSES)
    return {"total": len(rows), "saved": saved, "skipped": skipped, "errors": len(rows) - saved - skipped,
            "counts": counts, "labels": STATUS_LABELS, "rows": rows}

# Copyright (c) 2026, eCentric and contributors
"""Doc tep dinh kem cua phieu roi dua len Gemini - G2 cua "AI dien ho".

Module nay lam DUNG mot viec: bien mot danh sach `file_url` ma trinh duyet gui len thanh
danh sach phan `fileData` ma `gemini_api.generate_json` nhan duoc - va tu choi tat ca nhung
gi khong qua duoc cong.

CONG QUAN TRONG NHAT LA CONG QUYEN, khong phai cong mime.

  Trinh duyet gui len mot chuoi `/private/files/<ten>`. Neu server cu the ma doc thi BAT KY
  nguoi dung da dang nhap nao cung lay duoc noi dung tep cua nguoi khac: go ten tep vao o,
  AI doc ho va tra noi dung ra man hinh duoi dang "trich dan nguon". Do la mot duong ro du
  lieu hoan chinh, va no khong trong giong mot lo hong vi chang co dong SQL nao sai ca.

  `may_read` chi mo HAI cua:
    1. Chinh ho tai tep len (`File.owner`) - dung cho form "Tao moi", noi tep con mo coi
       (trang tai len qua /api/method/upload_file KHONG kem doctype/docname).
    2. Tep dang gan vao mot ho so ma ho co quyen doc - dung cho form "Sua / gui lai".
  Khong co cua thu ba. Role `System Manager` khong duoc mien: mien la mo lai dung cai cua
  vua dong.

HAI THU MODULE NAY CO TINH KHONG LAM:

  - KHONG chuyen doi Office -> PDF. Duong SharePoint lam duoc vi Graph chuyen ho; o day
    khong co ai chuyen. Gui .docx len Gemini thi no nhan roi doc ra rac, nen tu choi thang
    va noi ro phai xuat PDF - im lang nhan roi tra ket qua sai la te hon.
  - KHONG cache URI cua Gemini. URI song 48h, nhung cache mot URI het han thi lan goi sau
    hong ma khong ai hieu tai sao. Tai lai moi lan: cham hon vai giay, dung moi lan.
"""
import os
import time

import frappe

#: Tran cua PANEL trong form don. Khac han tran 10 PHIEU cua "Tao hang loat" (A61 §3):
#: cai kia dem QUYET DINH cua nguoi duyet, cai nay dem tep cua mot quyet dinh.
MAX_FILES = 5
MAX_BYTES_PER_FILE = 10 * 1024 * 1024
MAX_BYTES_TOTAL = 25 * 1024 * 1024
#: Ngan sach dong ho cho CA dot tai len. Mot request web khong duoc phep treo 5 x 60 giay.
BUDGET_SEC = 45

#: Kieu Gemini Files API doc duoc that. Danh sach nay la ALLOW-LIST: khong biet thi tu choi.
MIME_BY_EXT = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "heic": "image/heic",
    "heif": "image/heif",
    "txt": "text/plain",
    "md": "text/plain",
    "csv": "text/plain",
}

#: Tu choi RIENG voi loi khuyen, thay vi gop vao "kieu tep khong doc duoc".
OFFICE_EXTS = frozenset(("doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods"))

LY_DO = {
    "not_found": "không tìm thấy tệp",
    "no_permission": "bạn không có quyền đọc tệp này",
    "office": "định dạng Office — hãy lưu thành PDF rồi tải lại",
    "bad_type": "kiểu tệp AI không đọc được (chỉ PDF, ảnh, hoặc văn bản thuần)",
    "too_big": "tệp quá lớn",
    "total_too_big": "vượt tổng dung lượng cho một lượt",
    "over_cap": "quá số tệp cho một lượt",
    "empty": "tệp rỗng",
    "budget": "hết thời gian chờ tải lên",
    "upload_failed": "không tải lên được",
}


def ext_of(filename):
    """PURE. Duoi file, chu thuong, khong cham. '' neu khong co duoi."""
    base = str(filename or "").rsplit("/", 1)[-1]
    if "." not in base:
        return ""
    return base.rsplit(".", 1)[-1].strip().lower()


def mime_for(filename):
    """PURE. -> (mime, ly_do_tu_choi). Dung mot trong hai la None."""
    ext = ext_of(filename)
    if ext in MIME_BY_EXT:
        return MIME_BY_EXT[ext], None
    if ext in OFFICE_EXTS:
        return None, "office"
    return None, "bad_type"


def may_read(row, user=None):
    """Nguoi dang goi co duoc doc ban ghi File nay khong. Xem docstring dau module.

    `row` = dict co `owner`, `attached_to_doctype`, `attached_to_name`.
    """
    user = user or frappe.session.user
    if not row:
        return False
    if (row.get("owner") or "") == user:
        return True
    dt = row.get("attached_to_doctype")
    dn = row.get("attached_to_name")
    if dt and dn:
        try:
            return bool(frappe.has_permission(dt, doc=dn, ptype="read", user=user))
        except Exception:
            return False
    # Tep mo coi cua NGUOI KHAC: khong co ho so nao de hoi quyen -> khong mo.
    return False


#: Mot `file_url` co the ung voi NHIEU dong File - Frappe gop theo noi dung, nen hai nguoi
#: tai len cung mot tep se co hai dong tro cung mot URL. Quet co gioi han.
ROWS_PER_URL = 20


def _rows_for(file_url):
    """Cac ban ghi File theo `file_url`, hoac [] neu khong co.

    Tra theo BAN GHI chu khong ghep duong dan tu chuoi nguoi dung dua vao - cung ly do
    `sharepoint_mirror._noi_dung_tep` lam vay: chuoi ghep duoc thi tro ra ngoai kho duoc.

    Tra ve NHIEU dong chu khong mot dong: lay dai mot dong bat ky roi hoi quyen tren dong
    do thi mot nguoi CO quyen van bi tu choi chi vi truy van bat trung dong cua nguoi khac.
    """
    url = str(file_url or "").strip()
    if not url.startswith(("/files/", "/private/files/")):
        return []
    return frappe.get_all(
        "File", filters={"file_url": url},
        fields=["name", "file_name", "file_url", "owner", "file_size",
                "attached_to_doctype", "attached_to_name", "is_folder"],
        limit_page_length=ROWS_PER_URL, ignore_permissions=True) or []


def pick_readable(rows, user=None):
    """PURE ngoai `may_read`. -> (row_duoc_doc, co_dong_nao_khong).

    Khong co dong nao -> (None, False) = khong tim thay.
    Co dong nhung khong dong nao qua cong -> (None, True) = khong co quyen.
    """
    usable = [r for r in (rows or []) if not r.get("is_folder")]
    if not usable:
        return None, bool(rows)
    for row in usable:
        if may_read(row, user=user):
            return row, True
    return None, True


def _content_bytes(file_name):
    """Bytes cua tep. `File.get_content()` tra str khi noi dung giai ma duoc utf-8 (tep .txt)
    va bytes khi khong (PDF, anh) - chuan hoa ve bytes o day, mot cho."""
    doc = frappe.get_doc("File", file_name)
    data = doc.get_content()
    if isinstance(data, str):
        return data.encode("utf-8")
    return data or b""


def collect(file_urls, user=None, uploader=None, now=None):
    """-> (parts, rejected)

    parts    = [{"uri", "mime_type", "display_name"}] dua thang vao `generate_json(files=)`
    rejected = [{"file": <ten hien thi>, "reason": <ma>, "message": <cau tieng Viet>}]

    KHONG NEM. Mot tep hong khong duoc lam hong ca luot - nguoi dung van co ket qua tu
    nhung tep con lai va mot dong noi ro tep nao bi bo, vi sao.

    `uploader`/`now` tiem vao de test - mac dinh la duong that.
    """
    from ecentric_workspace import gemini_api
    uploader = uploader or gemini_api.upload_file_bytes
    now = now or time.time
    started = now()

    parts, rejected, total = [], [], 0

    def _no(label, reason):
        rejected.append({"file": label, "reason": reason,
                         "message": LY_DO.get(reason, reason)})

    urls = [u for u in (file_urls or []) if str(u or "").strip()]
    for over in urls[MAX_FILES:]:
        _no(os.path.basename(str(over)), "over_cap")

    for url in urls[:MAX_FILES]:
        rows = _rows_for(url)
        row, existed = pick_readable(rows, user=user)
        # Ten hien thi CHI lay tu dong da qua cong quyen. Khong qua duoc thi dung ten trong
        # duong dan nguoi dung vua gui - thu ho da biet - chu khong tra ten goc cua tep
        # nguoi khac ra man hinh.
        label = (row or {}).get("file_name") or os.path.basename(str(url))
        if not row:
            # Cung mot cau cho "khong co quyen" du ly do la gi o phia sau: noi ro hon = ke o
            # ngoai do duoc su ton tai cua tep.
            _no(label, "no_permission" if existed else "not_found")
            continue

        mime, why = mime_for(row.get("file_name") or url)
        if not mime:
            _no(label, why)
            continue

        size = int(row.get("file_size") or 0)
        if size > MAX_BYTES_PER_FILE:
            _no(label, "too_big")
            continue

        if now() - started > BUDGET_SEC:
            _no(label, "budget")
            continue

        try:
            data = _content_bytes(row["name"])
        except Exception:
            _no(label, "not_found")
            continue
        if not data:
            _no(label, "empty")
            continue
        # `file_size` la thu do TIN, khong phai thu do BIET: doc xong moi biet that su bao
        # nhieu byte. Kiem lai o day, khong chi o tren.
        if len(data) > MAX_BYTES_PER_FILE:
            _no(label, "too_big")
            continue
        if total + len(data) > MAX_BYTES_TOTAL:
            _no(label, "total_too_big")
            continue

        up = uploader(data, row.get("file_name") or label, mime)
        if not up or not up.get("success"):
            _no(label, "upload_failed")
            continue

        total += len(data)
        # `data` di kem de duong Kie dung duoc: Kie KHONG giai duoc URI cua
        # Google (URI tro ve generativelanguage.googleapis.com), no chi nhan
        # bytes inline. Bytes da co san o day roi nen khong phai tai lai lan hai;
        # thieu truong nay thi moi lan goi co tep deu roi ve Google.
        parts.append({"uri": up["uri"], "mime_type": mime,
                      "data": data,
                      "display_name": row.get("file_name") or label})

    return parts, rejected


def prompt_block(parts):
    """PURE. Doan chen vao prompt de model biet tep nao la tep nao.

    Khong co doan nay thi model thay N tai lieu khong ten; co no thi no trich dan duoc
    "theo hop-dong.pdf" - va nguoi dung doi chieu duoc.
    """
    if not parts:
        return ""
    lines = ["\nTEP DINH KEM (doc ca noi dung ben trong):"]
    for i, p in enumerate(parts, 1):
        lines.append("- Tep %d: %s" % (i, p.get("display_name") or "?"))
    return "\n".join(lines)

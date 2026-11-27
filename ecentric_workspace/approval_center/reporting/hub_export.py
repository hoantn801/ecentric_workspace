# Copyright (c) 2026, eCentric and contributors
"""Tai Excel / CSV tren trang hub /approvals/all-requests ("Tat ca yeu cau", 27/11/2026).

Ke toan loc DNTT tren hub roi muon mang danh sach di doi chieu. Tab "Tat ca" cua TUNG form da
co nut tai (shared/requests/all_list.export_all); hub thi chua.

TAI DUNG CAI DANG THAY - va KHONG HON. Ba dieu bao dam dieu do, deu nam o server:
  * Bo loc di qua `reporting.api.hub_filters` - CHINH ham ma bang hub (list_requests) dung.
    Tab (`box`) va `_me` lay tu session; client chi gui gia tri loc, khong gui danh sach ma
    phieu, khong gui ten cot, khong gui user.
  * Pham vi = `reporting.scope.resolve_scope(session.user)` + `scope_predicate` (trong
    queries._list_where), gom ca dieu kien PHIEU RIENG TU (shared/workflow/privacy.scope_sql).
    Dong nao khong hien tren bang thi khong co trong tep.
  * Cot xuat CHI lay tu dong `service.list_requests` da tra cho bang (ngay gui, ma, tieu de,
    loai, so tien, nguoi gui, nguoi nhan, phong ban, cap, trang thai, SLA). Khong doc them
    truong nghiep vu nao -> khong co duong nao de PII (CCCD doi tac KOL, luong...) lot vao
    tep ma khong lot len man hinh truoc.

Rang buoc giong export_all cua tab "Tat ca" (cung tran, cung kieu bao loi, cung ghi vet):
  * TRAN all_list.EXPORT_MAX dong. Vuot thi NEM LOI noi ro so dong + tran, khong cat bot.
  * GHI VET (Comment Info tren Web Page cua hub) TRUOC khi giao tep.
  * KHONG co quy tac chan export theo loai phieu nao: tab "Tat ca" cua form cung khong co
    (p198 chi go quyen `export` Desk cua role EC Finance tren EC Payment Request - duong
    /app/report, khong phai duong nay). Them luat chan thi phai them o CA hai noi.

Chong cong thuc trong tep: tieu de do nguoi dung go ("=HYPERLINK(...)") khong duoc thanh cong
thuc khi mo bang Excel - xlsx ep kieu chuoi, csv them dau nhay don truoc.
"""
import datetime
import json
import re

import frappe
from frappe import _

from ecentric_workspace.approval_center.reporting import api as _rapi
from ecentric_workspace.approval_center.reporting import queries as _q
from ecentric_workspace.approval_center.reporting import scope as _scope
from ecentric_workspace.approval_center.reporting import service as _service
from ecentric_workspace.approval_center.shared.requests import all_list as _al

#: Cung tran voi tab "Tat ca" cua tung form - mot cu bam khong keo ca lich su cong ty ra tep.
EXPORT_MAX = _al.EXPORT_MAX

#: Web Page cua hub (approval_center/ui/all_requests/page_sync ROUTE/NAME) - noi ghi vet. Ten
#: that do Frappe dat luc tao trang, nen tra theo route truoc, NAME chi la du phong.
PAGE_ROUTE = "approvals/all-requests"
PAGE_NAME = "approvals-all-requests"

#: Tab -> doan ten tep. Tab la / thieu = "Tat ca" (giong list_requests: khong them dieu kien).
TAB_SLUG = {
    "received": "da-nhan",
    "sent": "da-gui",
    "fulfil": "cho-toi-xu-ly",
    "watching": "toi-theo-doi",
    "all": "tat-ca",
}

#: (tieu de cot, kieu). Thu tu = thu tu cot tren bang hub; "Tien te" + "Qua han SLA" tach rieng
#: tu o "Chi phi" / o "Trang thai" de cot so tien la SO THAT (cong duoc trong Excel).
COLUMNS = (
    ("Ngày gửi", "date"),
    ("Mã", "text"),
    ("Tiêu đề", "text"),
    ("Loại", "text"),
    ("Chi phí", "money"),
    ("Tiền tệ", "text"),
    ("Người gửi", "text"),
    ("Người nhận", "text"),
    ("Phòng ban", "text"),
    ("Cấp hiện tại", "text"),
    ("Trạng thái", "text"),
    ("Quá hạn SLA", "text"),
)
_RONG = {"date": 18, "money": 16}
_RONG_CHU = (None, 22, 40, 24, None, 9, 26, 34, 28, 30, 18, 12)

#: Giong EcApprovalUI.levelText: ten cap chi la "Cap 2" / "Level 2" thi khong lap lai.
_TEN_CAP_TRONG = re.compile(r"^(cấp|level|bước)\s*\d+$", re.IGNORECASE | re.UNICODE)
_DAU_CONG_THUC = ("=", "+", "-", "@", "\t", "\r")


# --------------------------------------------------------------------------- #
# Mot dong cua bang -> mot dong cua tep (cung luat hien thi voi main_section.html)
# --------------------------------------------------------------------------- #
def _ff_dang_chay(v):
    return v.get("fulfillment_status") in ("Assigned", "In Progress")


def _ff_nhan(v):
    return "Chờ nhận xử lý" if v.get("fulfillment_status") == "Assigned" else "Đang xử lý"


def _cap(v):
    """O "Cap hien tai" - levelCell() cua hub."""
    if _ff_dang_chay(v):
        return _ff_nhan(v)
    try:
        n = int(v.get("current_level") or 0)
    except (TypeError, ValueError):
        n = 0
    ten = str(v.get("current_level_name") or "").strip()
    if not n:
        return ten
    dau = "Cấp %d" % n
    if not ten or _TEN_CAP_TRONG.match(ten):
        return dau
    return dau + " · " + ten


def _trang_thai(v):
    """O "Trang thai" - statusCell() cua hub (nhan tieng Viet, buoc xu ly ghi de)."""
    if _ff_dang_chay(v):
        ai = v.get("fulfillment_owner")
        nhan = _ff_nhan(v)
        return "%s (%s)" % (nhan, ai) if (ai and v.get("fulfillment_status") != "Assigned") else nhan
    goc = v.get("status_label") or v.get("status") or ""
    return _al.TRANG_THAI_VI.get(goc, goc)


def _ngay(s):
    """'2026-08-25 18:21:00[.ffffff]' -> datetime (o ngay that trong Excel). Hong -> chuoi goc."""
    s = str(s or "").strip()
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return s


def _so(v):
    """So tien -> so (int neu tron). Trong va 0 la HAI chuyen khac nhau: trong giu trong."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return int(n) if n.is_integer() else n


def dong(v):
    """Danh sach gia tri theo COLUMNS. CHI doc khoa cua dong bang hub - khong gi khac."""
    gui = v.get("requester_info") or {}
    nguoi_gui = gui.get("name") or gui.get("user") or v.get("requester") or ""
    nhan = ", ".join(x for x in ((p or {}).get("name") or (p or {}).get("user") or ""
                                 for p in (v.get("sent_to") or [])) if x)
    tien = _so(v.get("amount"))
    tt = str(v.get("currency") or "").upper()
    if not tt and tien is not None:
        tt = "VND"
    return [
        _ngay(v.get("submitted_at")),
        v.get("name") or "",
        v.get("title") or v.get("type") or "",
        v.get("type") or "",
        tien,
        tt,
        nguoi_gui,
        nhan,
        v.get("department") or "",
        _cap(v),
        _trang_thai(v),
        "Có" if v.get("sla_breached") else "",
    ]


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #
def export(filters=None, search=None, box=None, fmt="xlsx"):
    """Xuat TOAN BO ket qua cua tab + bo loc (khong chi trang dang xem), trong pham vi nguoi goi."""
    fmt = "csv" if fmt == "csv" else "xlsx"
    search = (search or None)
    scope = _scope.resolve_scope(frappe.session.user)
    f = _rapi.hub_filters(filters, box)

    tong = _q.count_requests(scope, f, search)
    _chan_vuot_tran(tong)
    if not tong:
        frappe.throw(_("Không có yêu cầu nào khớp tab và bộ lọc hiện tại để tải."))
    out = _service.list_requests(scope, f, start=0, page_length=EXPORT_MAX, search=search)
    # Giua luc dem va luc doc co phieu moi: van khong am tham cat bot o tran.
    _chan_vuot_tran(out.get("total") or 0)
    rows = out.get("rows") or []
    bang = [dong(v) for v in rows]

    # GHI VET TRUOC khi giao tep (giong export_all): ghi sau thi loi giua chung lam tep di
    # ra ma vet khong co.
    _ghi_vet(scope, f, search, box, len(bang), fmt)

    tab = box if box in TAB_SLUG else "all"
    ten = "tat-ca-yeu-cau_%s_%s" % (TAB_SLUG[tab],
                                    frappe.utils.now_datetime().strftime("%Y%m%d-%H%M"))
    tieu_de = [c for c, _k in COLUMNS]
    if fmt == "csv":
        frappe.response["filename"] = ten + ".csv"
        frappe.response["filecontent"] = _al._csv([tieu_de] + [_dong_csv(r) for r in bang])
    else:
        frappe.response["filename"] = ten + ".xlsx"
        frappe.response["filecontent"] = _xlsx(tieu_de, bang)
    frappe.response["type"] = "binary"


def _chan_vuot_tran(tong):
    if tong > EXPORT_MAX:
        frappe.throw(_("Tab và bộ lọc đang khớp {0} yêu cầu, vượt mức {1} cho một lần tải. "
                       "Hãy thu hẹp khoảng ngày hoặc thêm bộ lọc rồi thử lại.")
                     .format(tong, EXPORT_MAX))


def _chu_an_toan(x):
    """CSV: chuoi bat dau bang = + - @ (cong thuc) -> them ' phia truoc."""
    if isinstance(x, str) and x[:1] in _DAU_CONG_THUC:
        return "'" + x
    return x


def _dong_csv(r):
    out = []
    for (_c, kieu), x in zip(COLUMNS, r):
        if x is None:
            out.append("")
        elif kieu == "date" and isinstance(x, datetime.datetime):
            # ISO: khong nham ngay/thang du Excel dat locale nao.
            out.append(x.strftime("%Y-%m-%d %H:%M"))
        else:
            out.append(_chu_an_toan(x))
    return out


def _xlsx(tieu_de, bang):
    """openpyxl truc tiep (make_xlsx khong dat dinh dang so/ngay): cot ngay la o NGAY, cot tien
    la o SO co phan cach, dong dau dam + co dinh + co nut loc."""
    import io

    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Tất cả yêu cầu"
    for j, t in enumerate(tieu_de, 1):
        ws.cell(row=1, column=j, value=t).font = Font(bold=True)
    for i, r in enumerate(bang, 2):
        for j, ((_c, kieu), x) in enumerate(zip(COLUMNS, r), 1):
            if x is None:
                continue
            if isinstance(x, str):
                x = ILLEGAL_CHARACTERS_RE.sub("", x)
            o = ws.cell(row=i, column=j, value=x)
            if isinstance(x, str):
                o.data_type = "s"          # "=..." do nguoi dung go KHONG thanh cong thuc
            elif kieu == "date" and isinstance(x, datetime.datetime):
                o.number_format = "dd/mm/yyyy hh:mm"
            elif kieu == "money":
                o.number_format = "#,##0" if isinstance(x, int) else "#,##0.00"
    for j, (_c, kieu) in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(j)].width = _RONG.get(kieu) or _RONG_CHU[j - 1] or 16
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(COLUMNS)), max(1, len(bang) + 1))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _ghi_vet(scope, f, search, box, so_dong, fmt):
    """Ai tai, tab nao, loc gi, bao nhieu dong. Khong ngan ai lam gi - de tra nguoc khi can."""
    try:
        trang = frappe.db.get_value("Web Page", {"route": PAGE_ROUTE}, "name") or PAGE_NAME
        doc = frappe.get_doc({
            "doctype": "Comment", "comment_type": "Info",
            "reference_doctype": "Web Page", "reference_name": trang,
            "content": "Export hub Tất cả yêu cầu: %d dòng, định dạng %s, tab %s, phạm vi %s, "
                       "bộ lọc %s%s" % (
                           so_dong, fmt, box or "all", scope.get("mode"),
                           json.dumps(f, ensure_ascii=False, default=str),
                           (", tìm: " + search) if search else ""),
        })
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ghi vet export hub all-requests")

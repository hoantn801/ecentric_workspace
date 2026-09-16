# Copyright (c) 2026, eCentric and contributors
"""Tab "Tat ca" cua TUNG form: danh sach moi phieu nguoi dung duoc phep xem, co loc + export.

VI SAO KHONG VIET TRUY VAN MOI. Trang /approvals/all-requests da co san mot danh sach lien
form DA DUOC KIEM SOAT QUYEN: `reporting.scope.resolve_scope` phan nguoi dung thanh bon bac
(admin / truong phong / nguoi duyet / nguoi de nghi), `scope_predicate` tra ve manh SQL
tham-so-hoa PHAI duoc AND vao moi truy van, va `reporting.service.list_requests` da lo phan
loc, tim kiem, phan trang, SLA, tieu de + so tien lay tu DocType nghiep vu.

Tab nay = DUNG LAI y nguyen bo may do, chi GHIM `approval_type` ve dung form dang mo. Khong
mo hinh quyen thu hai, khong ban sao truy van thu hai de hai ben troi nhau sau vai thang.

GHIM LA VIEC CUA SERVER. `approval_type` do CLIENT gui len bi GHI DE, khong phai duoc hop
nhat: neu chi "mac dinh khi client khong gui" thi mot request tu che co the doi sang form
khac va tab "Tat ca" cua Booking se tra ve phieu thanh toan. Bo loc o trinh duyet la tien
nghi hien thi, KHONG BAO GIO la ranh gioi bao mat (doc lai docstring cua reporting.scope).

EXPORT. Hoan chot 16/09: ai thay duoc tab thi export duoc. Dieu do KHONG mau thuan voi
`reporting.scope.can_export` (chi admin) - ham do canh viec xuat TOAN BO du lieu toan cong ty
tren trang all-requests. O day moi luot xuat van di qua dung `scope_predicate`, nen "tat ca"
cua moi nguoi la tat ca CUA HO. An toan den tu vi tu, khong den tu viec an nut.

Ba rang buoc di kem, khong phai trang tri:
  * TRAN dong (EXPORT_MAX). Mot cu bam khong duoc keo ca lich su thanh toan cua cong ty ra
    file. Vuot tran thi bao thu hep bo loc, khong am tham cat bot.
  * GHI VET moi luot xuat (ai, loc gi, bao nhieu dong). Tep chua ten nguoi thu huong va so
    tai khoan ngan hang; khi can biet mot tep ro ri di tu dau thi phai co cho tra.
  * Tong tien chi tinh khi so phieu <= SUM_MAX. Mot phep cong khong gioi han chay theo tung
    lan go phim la cach bien mot o tim kiem thanh mot cuoc tan cong vao chinh database.
"""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.reporting import api as _rapi
from ecentric_workspace.approval_center.reporting import queries as _q
from ecentric_workspace.approval_center.reporting import scope as _scope
from ecentric_workspace.approval_center.reporting import service as _service
from ecentric_workspace.approval_center.reporting import status as _status

EXPORT_MAX = 5000
SUM_MAX = 2000
PAGE_MAX = 100


def _pinned_filters(definition, filters):
    """Bo loc da chuan hoa, voi approval_type BI GHI DE ve form nay."""
    f = _rapi._parse_filters(filters, force_date=False)
    f["approval_type"] = definition.code          # ghi de, khong phai mac dinh
    return f


def _tong_tien(definition, rows_total, scope, f, search):
    """Tong so tien cua CA bo ket qua loc, khong chi trang dang xem.

    Tra None khi vuot SUM_MAX - man hinh hien "-" kem goi y thu hep bo loc. Tha noi
    "khong tinh" con hon dua mot con so chi dung cho 50 dong dau ma trong nhu tong."""
    if not rows_total or rows_total > SUM_MAX:
        return None
    meta = frappe.get_meta(definition.business_doctype)
    field = next((c for c in ("payment_amount", "total_amount", "expected_budget", "amount")
                  if meta.has_field(c)), None)
    if not field:
        return None
    refs = [r["reference_name"] for r in _q.fetch_requests_page(scope, f, 0, SUM_MAX, search)
            if r.get("reference_name")]
    if not refs:
        return 0
    tong = 0
    for row in frappe.get_all(definition.business_doctype,
                              filters={"name": ["in", refs]}, fields=[field]):
        tong += float(row.get(field) or 0)
    return tong


def list_all(definition, filters=None, start=0, page_length=50, search=None):
    scope = _scope.resolve_scope(frappe.session.user)
    f = _pinned_filters(definition, filters)
    try:
        start = max(0, int(start))
        page_length = min(PAGE_MAX, max(1, int(page_length)))
    except (TypeError, ValueError):
        start, page_length = 0, 50
    out = _service.list_requests(scope, f, start=start, page_length=page_length,
                                 search=(search or None))
    out["scope_mode"] = scope.get("mode")
    out["total_amount"] = _tong_tien(definition, out.get("total") or 0, scope, f, search or None)
    out["sum_capped"] = bool((out.get("total") or 0) > SUM_MAX)
    return out


def filter_options(definition):
    """Chi nhung gia tri co that TRONG PHAM VI cua nguoi dung VA trong form nay.

    Khong liet ke phong ban ho khong duoc xem: mot o chon bay ra ten phong ban la mot ro ri
    nho, va con day nguoi dung chon roi nhan ve danh sach rong ma khong hieu vi sao."""
    scope = _scope.resolve_scope(frappe.session.user)
    sp, params = _scope.scope_predicate(scope)
    params["ft_type"] = definition.code
    where = sp + " AND r.approval_type = %(ft_type)s"
    depts = frappe.db.sql(
        "SELECT DISTINCT r.requester_department AS v FROM `tabEC Approval Request` r "
        "WHERE " + where + " AND r.requester_department IS NOT NULL "
        "ORDER BY r.requester_department", params, as_dict=True)
    reqs = frappe.db.sql(
        "SELECT DISTINCT r.requested_by AS v, u.full_name AS label "
        "FROM `tabEC Approval Request` r LEFT JOIN `tabUser` u ON u.name = r.requested_by "
        "WHERE " + where + " AND r.requested_by IS NOT NULL ORDER BY u.full_name",
        params, as_dict=True)
    return {
        "departments": [d["v"] for d in depts],
        "requesters": [{"value": r["v"], "label": r.get("label") or r["v"]} for r in reqs],
        "statuses": _status.NORMALIZED_STATUSES,
        "scope_mode": scope.get("mode"),
    }


_COT = (
    ("name", "Ma phieu"), ("submitted_at", "Ngay gui"), ("title", "Tieu de"),
    ("requester_name", "Nguoi de nghi"), ("department", "Phong ban"),
    ("amount", "So tien"), ("currency", "Tien te"),
    ("status_label", "Trang thai"), ("current_level", "Buoc"),
    ("current_level_name", "Ten buoc"), ("waiting_on", "Dang cho ai"),
    ("sla_due_at", "Han SLA"), ("sla_breached", "Qua han"),
    ("fulfillment_status", "Trang thai xu ly"),
)


def _o_xuat(v):
    """Mot dong da lam phang cho tep xuat ra."""
    ai = ", ".join(a.get("name") or a.get("user") or ""
                   for a in (v.get("approvers") or []) if (a.get("status") == "Pending"))
    d = dict(v)
    d["requester_name"] = (v.get("requester_info") or {}).get("name") or v.get("requester") or ""
    d["waiting_on"] = ai
    d["sla_breached"] = "x" if v.get("sla_breached") else ""
    return [d.get(k) if d.get(k) is not None else "" for k, _lab in _COT]


def export_all(definition, filters=None, search=None, fmt="xlsx"):
    """Xuat TOAN BO ket qua loc (khong phai trang dang xem), trong pham vi cua nguoi goi."""
    scope = _scope.resolve_scope(frappe.session.user)
    f = _pinned_filters(definition, filters)
    search = search or None
    tong = _q.count_requests(scope, f, search)
    if tong > EXPORT_MAX:
        frappe.throw(_("Bộ lọc đang khớp {0} phiếu, vượt mức {1} cho một lần xuất. "
                       "Hãy thu hẹp khoảng ngày hoặc thêm bộ lọc rồi thử lại.")
                     .format(tong, EXPORT_MAX))
    out = _service.list_requests(scope, f, start=0, page_length=EXPORT_MAX, search=search)
    rows = out.get("rows") or []

    tieu_de = [lab for _k, lab in _COT]
    bang = [tieu_de] + [_o_xuat(v) for v in rows]

    # GHI VET TRUOC khi giao tep. Ghi sau thi mot loi lam tep van di ra ma vet thi khong co.
    _ghi_vet(definition, scope, f, search, len(rows), fmt)

    ten = "%s_%s" % (definition.code.lower(),
                     frappe.utils.now_datetime().strftime("%Y%m%d_%H%M"))
    if fmt == "csv":
        frappe.response["filename"] = ten + ".csv"
        frappe.response["filecontent"] = _csv(bang)
        frappe.response["type"] = "binary"
        return
    frappe.response["filename"] = ten + ".xlsx"
    frappe.response["filecontent"] = _xlsx(bang, definition.code)
    frappe.response["type"] = "binary"


def _csv(bang):
    """CSV kem BOM UTF-8. Thieu BOM thi Excel tren Windows doc tieng Viet thanh ky tu rac -
    va nguoi nhan se doi loi cho he thong chu khong cho Excel."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in bang:
        w.writerow(["" if c is None else c for c in r])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _xlsx(bang, ten_sheet):
    from frappe.utils.xlsxutils import make_xlsx
    return make_xlsx(bang, ten_sheet[:31] or "Export").getvalue()


def _ghi_vet(definition, scope, f, search, so_dong, fmt):
    """Ai xuat, loc gi, bao nhieu dong. Khong ngan ai lam gi - de tra nguoc khi can."""
    try:
        frappe.get_doc({
            "doctype": "Comment", "comment_type": "Info",
            "reference_doctype": "EC Approval Type", "reference_name": definition.code,
            "content": "Export %s: %d dòng, định dạng %s, phạm vi %s, bộ lọc %s%s" % (
                definition.code, so_dong, fmt, scope.get("mode"),
                json.dumps(f, ensure_ascii=False, default=str),
                (", tìm: " + search) if search else ""),
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ghi vet export %s" % definition.code)

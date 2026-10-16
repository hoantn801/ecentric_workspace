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

LOC THEM / SAP XEP / COT RIENG (16/10/2026, Finance gop y tren Contract Review, PO duyet).
Bon thu, deu nam o tang dung chung nay de 28 form cung huong:
  * Sap xep `filters.sort` thuoc mot danh sach TRANG (`queries.SORT_KEYS`). Gia tri la ->
    mac dinh moi -> cu. Khong co ORDER BY nao do client viet.
  * Khoang so tien `filters.amount_min/amount_max` - chi khi form CO truong so tien, va
    truong do la DUNG truong cot "So tien" dang hien (business_summary.AMOUNT_FIELDS).
    Loc mot truong khac voi truong dang hien la noi doi nguoi dung.
  * Cot them + o loc chon theo truong nghiep vu: form tu khai `all_tab_columns` /
    `all_tab_filters` tren ApprovalDefinition. Ten truong chi duoc nhan neu (a) definition
    khai VA (b) meta cua DocType nghiep vu co that. Client chi gui GIA TRI, khong bao gio
    gui ten cot vao SQL.
  * Gia tri cho o loc chon lay tu nhung phieu NGUOI XEM DUOC THAY (scope_predicate + ghim
    form), giong dung luat cua o "phong ban" o duoi.
Ca bon di qua cung `_pinned_filters`, nen bang, tong tien va tep xuat luon khop nhau.
"""
import json
import math
import re

import frappe
from frappe import _

from ecentric_workspace.approval_center.reporting import api as _rapi
from ecentric_workspace.approval_center.reporting import business_summary as _bsum
from ecentric_workspace.approval_center.reporting import queries as _q
from ecentric_workspace.approval_center.reporting import scope as _scope
from ecentric_workspace.approval_center.reporting import service as _service
from ecentric_workspace.approval_center.reporting import status as _status

# Tu dien trang thai LAY NGUYEN cua trang hub (/approvals/all-requests, statusLabel).
# Tang bao cao tra ve nhan tieng Anh ("Pending", "Rejected"); moi man hinh khac cua
# Approval Center hien tieng Viet. Dich o day - mot lan, ca bang lan TEP XUAT RA - thay vi
# dich trong bundle: lam vay thi man hinh tieng Viet ma tep ke toan mo ra lai tieng Anh.
# Che them mot tu dien thu ba la cach chac chan de vai thang nua ba ban troi nhau.
TRANG_THAI_VI = {
    "Draft": "Nháp",
    "Pending": "Chờ duyệt",
    "Information Required": "Cần bổ sung",
    "Completed": "Hoàn tất",
    "Approved": "Đã duyệt",
    "Rejected": "Từ chối",
    "Cancelled": "Đã hủy",
    "In Progress": "Đang xử lý",
}

#: Tran so ma phieu tra duoc theo tieu de cho mot luot tim. Dong bo voi queries.SEARCH_REF_MAX.
SEARCH_REF_MAX = 500

EXPORT_MAX = 5000
SUM_MAX = 2000
PAGE_MAX = 100
#: Tran so gia tri trong MOT o loc chon. Mot o chon 5000 dong khong ai dung duoc, va mot
#: DISTINCT khong gioi han chay moi lan mo tab la tai vo ich len database.
DISTINCT_MAX = 500
#: Do dai toi da cua gia tri mot o loc chon (Data/Select cua Frappe = 140).
GIA_TRI_MAX = 140

#: Truong so tien du phong cho TONG khi DocType chua khai trong AMOUNT_FIELDS (hanh vi cu).
_TIEN_DU_PHONG = ("payment_amount", "total_amount", "expected_budget", "amount")
_TEN_TRUONG = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_TEN_DOCTYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,139}$")
_SO_KIEU_VN = re.compile(r"^\d{1,3}(\.\d{3})+$")


def _doc_bo_loc(filters):
    if isinstance(filters, str):
        try:
            filters = json.loads(filters or "{}")
        except Exception:
            filters = {}
    return filters if isinstance(filters, dict) else {}


def _pinned_filters(definition, filters, search=None):
    """Bo loc da chuan hoa, voi approval_type BI GHI DE ve form nay."""
    goc = _doc_bo_loc(filters)
    f = _rapi._parse_filters(goc, force_date=False)
    f["approval_type"] = definition.code          # ghi de, khong phai mac dinh
    if search:
        f["_search_refs"] = _ma_theo_tieu_de(definition, search)
    _loc_nghiep_vu(definition, goc, f)
    return f


def _truong_tien(definition, meta=None):
    """Truong so tien cua form = DUNG truong cot "So tien" dang hien (AMOUNT_FIELDS).

    Khong khai / meta khong co -> None: form nay khong co loc + sap xep theo so tien."""
    khai = (_bsum.AMOUNT_FIELDS.get(definition.business_doctype) or (None,))[0]
    if not khai or not _TEN_TRUONG.match(khai):
        return None
    meta = meta or frappe.get_meta(definition.business_doctype)
    return khai if meta.has_field(khai) else None


def _cot_them(definition, meta):
    """[(nhan, fieldname, kieu)] da kiem: definition khai VA DocType nghiep vu co that."""
    out, da = [], set()
    for cot in getattr(definition, "all_tab_columns", ()) or ():
        try:
            nhan, fn, kieu = cot
        except (TypeError, ValueError):
            continue
        if fn in da or not _TEN_TRUONG.match(str(fn)) or not meta.has_field(fn):
            continue
        da.add(fn)
        out.append((nhan, fn, kieu))
    return out


def _loc_them(definition, meta):
    """Fieldname co o loc chon: definition khai VA DocType nghiep vu co that."""
    out = []
    for fn in getattr(definition, "all_tab_filters", ()) or ():
        if (isinstance(fn, str) and _TEN_TRUONG.match(fn) and fn not in out
                and meta.has_field(fn)):
            out.append(fn)
    return out


def _so_tien(v):
    """So tien tu client -> float >= 0, hoac None (bo qua o loc, khong nem loi).

    Client gui SO (EcMoney.parse). Chuoi kieu Viet "1.500.000" van duoc hieu dung; chuoi
    khong phai so, so am, NaN/vo cuc -> None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        s = str(v).strip().replace(" ", "")
        if not s:
            return None
        if _SO_KIEU_VN.match(s):
            s = s.replace(".", "")
        try:
            n = float(s)
        except ValueError:
            return None
    if math.isnan(n) or math.isinf(n) or n < 0:
        return None
    return n


def _loc_nghiep_vu(definition, goc, f):
    """Dat `_biz` (dieu kien tren DocType nghiep vu) + `_sort` vao bo loc da ghim.

    Chi ten truong da kiem (`_loc_them`, `_truong_tien`) moi vao duoc dac ta; tu client chi
    lay GIA TRI. Khong co gi de loc/sap xep -> khong dat khoa nao (hub y nhu cu)."""
    meta = frappe.get_meta(definition.business_doctype)
    tien = _truong_tien(definition, meta)
    eq = []
    them = goc.get("extra") if isinstance(goc.get("extra"), dict) else {}
    for fn in _loc_them(definition, meta):
        v = them.get(fn)
        if isinstance(v, bool) or not isinstance(v, (str, int, float)):
            continue
        v = str(v).strip()
        if v:
            eq.append((fn, v[:GIA_TRI_MAX]))
    lo = _so_tien(goc.get("amount_min")) if tien else None
    hi = _so_tien(goc.get("amount_max")) if tien else None
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo                      # go nguoc hai dau thi hieu y, khong tra rong
    sort = goc.get("sort")
    if sort not in _q.SORT_KEYS or sort == "newest":
        sort = None
    elif sort.startswith("amount_") and not tien:
        sort = None
    if sort:
        f["_sort"] = sort
    if eq or lo is not None or hi is not None or (sort or "").startswith("amount_"):
        f["_biz"] = {"doctype": definition.business_doctype, "amount_field": tien,
                     "eq": tuple(eq), "amount_min": lo, "amount_max": hi}
    return f


def _gan_cot_them(definition, rows, cot):
    """Gan v["extra"] = {fieldname: gia tri} cho TRANG dang xem. Mot truy van, theo lo.

    Chi doc dung nhung phieu da qua scope_predicate (rows). Loi o day khong duoc lam trang
    trang - bang van hien, chi thieu cot them."""
    if not rows:
        return rows
    for v in rows:
        v["extra"] = {}
    if not cot:
        return rows
    refs = [v.get("reference_name") for v in rows if v.get("reference_name")]
    if not refs:
        return rows
    truong = [fn for _n, fn, _k in cot]
    try:
        theo_ma = {r["name"]: r for r in frappe.get_all(
            definition.business_doctype, filters={"name": ["in", refs]},
            fields=["name"] + truong, limit_page_length=0)}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "all_list cot them %s" % definition.code)
        return rows
    for v in rows:
        d = theo_ma.get(v.get("reference_name")) or {}
        v["extra"] = {fn: d.get(fn) for fn in truong}
    return rows


def _ma_theo_tieu_de(definition, search):
    """Ma phieu co TIEU DE chua `search`.

    Vi sao can. Tieu de that nam o DocType nghiep vu, khong o `EC Approval Request`, nen
    menh de tim kiem cua tang bao cao khong voi toi. Ket qua: go "CMC" vao o tim kiem ra
    KHONG PHIEU NAO trong khi cot "Tieu de" ngay tren man hinh dang hien hai phieu co chu
    do (do tren production 16/09). Mot o tim kiem khong tim duoc thu dang hien ngay canh no
    thi te hon khong co o tim kiem - nguoi dung ket luan "he thong khong co phieu".

    KHONG NOI RONG QUYEN: danh sach ma nay chi la mot ve OR trong menh de tim, va menh de
    do van duoc AND voi scope_predicate o `_list_where`.
    """
    meta = frappe.get_meta(definition.business_doctype)
    if not meta.has_field("request_title"):
        return []
    rows = frappe.get_all(definition.business_doctype,
                          filters={"request_title": ["like", "%" + str(search).strip() + "%"]},
                          fields=["name"], limit_page_length=SEARCH_REF_MAX)
    return [r["name"] for r in rows]


def _viet_hoa(rows):
    """Gan nhan tieng Viet vao tung dong. Giu nguyen `status` goc de bo loc van khop."""
    for v in rows or []:
        v["status_label"] = TRANG_THAI_VI.get(v.get("status_label") or v.get("status"),
                                              v.get("status_label") or v.get("status") or "")
    return rows


def _tong_tien(definition, rows_total, scope, f, search):
    """Tong so tien cua CA bo ket qua loc, khong chi trang dang xem.

    Tra None khi vuot SUM_MAX - man hinh hien "-" kem goi y thu hep bo loc. Tha noi
    "khong tinh" con hon dua mot con so chi dung cho 50 dong dau ma trong nhu tong."""
    if not rows_total or rows_total > SUM_MAX:
        return None
    meta = frappe.get_meta(definition.business_doctype)
    # Cong DUNG truong cot "So tien" dang hien; DocType chua khai thi giu cach do cu.
    # Form co truong TIEN TE rieng (AI Topup: USD lan VND) thi KHONG cong: cong 100 USD voi
    # 2.500.000 VND ra mot con so trong nhu tong ma sai hoan toan.
    field = None
    if not (_bsum.AMOUNT_FIELDS.get(definition.business_doctype) or (None, None))[1]:
        field = _truong_tien(definition, meta)
    field = field or next((c for c in _TIEN_DU_PHONG if meta.has_field(c)), None)
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
    f = _pinned_filters(definition, filters, search)
    try:
        start = max(0, int(start))
        page_length = min(PAGE_MAX, max(1, int(page_length)))
    except (TypeError, ValueError):
        start, page_length = 0, 50
    out = _service.list_requests(scope, f, start=start, page_length=page_length,
                                 search=(search or None))
    _viet_hoa(out.get("rows"))
    _gan_cot_them(definition, out.get("rows"),
                  _cot_hien(definition, frappe.get_meta(definition.business_doctype)))
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
    meta = frappe.get_meta(definition.business_doctype)
    tien = _truong_tien(definition, meta)
    cot = _cot_them(definition, meta)
    nhan_tien = next((n for n, fn, _k in cot if fn == tien), None)
    nhan_cot = {fn: n for n, fn, _k in cot}
    loc = []
    for fn in _loc_them(definition, meta):
        loc.append({"fieldname": fn, "label": nhan_cot.get(fn) or _nhan_truong(meta, fn),
                    "options": _gia_tri_rieng(definition, fn, where, dict(params))})
    return {
        "departments": [d["v"] for d in depts],
        "requesters": [{"value": r["v"], "label": r.get("label") or r["v"]} for r in reqs],
        # Gia tri gui len server giu nguyen tieng Anh (engine doc no); chi NHAN la tieng
        # Viet. Dich ca gia tri thi bo loc im lang khong khop gi ca.
        "statuses": [{"value": x, "label": TRANG_THAI_VI.get(x, x)}
                     for x in _status.NORMALIZED_STATUSES],
        "scope_mode": scope.get("mode"),
        # None = form khong co so tien -> man hinh khong ve o "so tien tu/den" lan sap xep
        # theo so tien.
        "amount": {"field": tien, "label": nhan_tien or "Số tiền"} if tien else None,
        "columns": [{"label": n, "fieldname": fn, "kind": k}
                    for n, fn, k in _cot_hien(definition, meta)],
        "extra_filters": loc,
    }


def _cot_hien(definition, meta):
    """Cot them THAT SU ve them: bo cot trung truong so tien (da co cot "So tien")."""
    tien = _truong_tien(definition, meta)
    return [c for c in _cot_them(definition, meta) if c[1] != tien]


def _nhan_truong(meta, fn):
    try:
        df = meta.get_field(fn)
        return (getattr(df, "label", None) or fn) if df else fn
    except Exception:
        return fn


def _gia_tri_rieng(definition, fn, where, params):
    """Gia tri KHAC NHAU cua mot truong nghiep vu, CHI tren phieu nguoi xem duoc thay.

    `where` da mang scope_predicate + ghim form (xem filter_options). fn da qua `_loc_them`
    (definition khai + meta co) va regex; ten DocType tu definition, khong tu client."""
    if not (_TEN_TRUONG.match(fn) and _TEN_DOCTYPE.match(definition.business_doctype or "")):
        return []
    params["ft_dt"] = definition.business_doctype
    params["ft_max"] = DISTINCT_MAX
    rows = frappe.db.sql(
        "SELECT DISTINCT b.`" + fn + "` AS v FROM `tabEC Approval Request` r "
        "JOIN `tab" + definition.business_doctype + "` b ON b.name = r.reference_name "
        "WHERE " + where + " AND r.reference_doctype = %(ft_dt)s "
        "AND b.`" + fn + "` IS NOT NULL AND b.`" + fn + "` != '' "
        "ORDER BY v LIMIT %(ft_max)s", params, as_dict=True)
    return [r["v"] for r in rows]


_COT = (
    ("name", "Ma phieu"), ("submitted_at", "Ngay gui"), ("title", "Tieu de"),
    ("requester_name", "Nguoi de nghi"), ("department", "Phong ban"),
    ("amount", "So tien"), ("currency", "Tien te"),
    ("status_label", "Trang thai"), ("current_level", "Buoc"),
    ("current_level_name", "Ten buoc"), ("waiting_on", "Dang cho ai"),
    ("sla_due_at", "Han SLA"), ("sla_breached", "Qua han"),
    ("fulfillment_status", "Trang thai xu ly"),
)


def _o_xuat(v, cot=()):
    """Mot dong da lam phang cho tep xuat ra. Cot them (definition) noi SAU cot co dinh -
    vi tri cac cot cu khong doi, ai da quen doc tep thi doc tiep duoc."""
    ai = ", ".join(a.get("name") or a.get("user") or ""
                   for a in (v.get("approvers") or []) if (a.get("status") == "Pending"))
    d = dict(v)
    d["requester_name"] = (v.get("requester_info") or {}).get("name") or v.get("requester") or ""
    d["waiting_on"] = ai
    d["sla_breached"] = "x" if v.get("sla_breached") else ""
    them = v.get("extra") or {}
    return ([d.get(k) if d.get(k) is not None else "" for k, _lab in _COT] +
            [them.get(fn) if them.get(fn) is not None else "" for _n, fn, _k in cot])


def export_all(definition, filters=None, search=None, fmt="xlsx"):
    """Xuat TOAN BO ket qua loc (khong phai trang dang xem), trong pham vi cua nguoi goi."""
    scope = _scope.resolve_scope(frappe.session.user)
    search = search or None
    f = _pinned_filters(definition, filters, search)
    tong = _q.count_requests(scope, f, search)
    if tong > EXPORT_MAX:
        frappe.throw(_("Bộ lọc đang khớp {0} phiếu, vượt mức {1} cho một lần xuất. "
                       "Hãy thu hẹp khoảng ngày hoặc thêm bộ lọc rồi thử lại.")
                     .format(tong, EXPORT_MAX))
    out = _service.list_requests(scope, f, start=0, page_length=EXPORT_MAX, search=search)
    rows = _viet_hoa(out.get("rows") or [])
    cot = _cot_hien(definition, frappe.get_meta(definition.business_doctype))
    _gan_cot_them(definition, rows, cot)

    tieu_de = [lab for _k, lab in _COT] + [n for n, _fn, _k in cot]
    bang = [tieu_de] + [_o_xuat(v, cot) for v in rows]

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

# Copyright (c) 2026, eCentric and contributors
"""Dong hop dong tren ho so nhan su (`Employee.ec_contracts` -> EC Employee Contract) - luat THUAN.

KHONG import frappe: nhan dict, tra dict / ngay. Ca form "Danh gia nhan su" (approval_center/
features/employee_review) lan job khao sat theo moc (surveys/application/ca_nhan) deu doc NGAY
tu day - mot khai niem, mot cho tinh (Hoan chot 22/11: "ngay ket thuc lay tu bang hop dong co
san tren ho so, khong them truong moi").

Dong hop dong (dict): name, loai_hop_dong, tu_ngay, den_ngay, khong_thoi_han.
Ngay le (`ngay_le`) truyen vao - tap `datetime.date` lay tu
approval_center.shared.workflow.ngay_lam_viec.ngay_le_cong_ty() o tang ngoai.
"""
import calendar
import datetime as _dt

THU_VIEC = "Thử việc"
THUC_TAP = "Thực tập"
HDLD_PREFIX = "HĐLĐ lần "
HDLD_MAX = 5

#: Loai danh gia (truong `review_type` cua EC Employee Review).
DG_THU_VIEC = "Thử việc"
DG_THUC_TAP = "Thực tập"
DG_HOP_DONG = "Hợp đồng"
LOAI_DANH_GIA = (DG_THU_VIEC, DG_THUC_TAP, DG_HOP_DONG)

#: (nhap som truoc, tu gui truoc) - so ngay LICH truoc `den_ngay` (Hoan chot 22-23/11):
#: thu viec / thuc tap nhap D-21, tu gui D-14; hop dong nhap D-37, tu gui D-30.
LICH_DANH_GIA = {DG_THU_VIEC: (21, 14), DG_THUC_TAP: (21, 14), DG_HOP_DONG: (37, 30)}

#: employment_type tren Employee can co dong hop dong co ngay ket thuc (hoac khong thoi han).
ET_PROBATION = "Probation"
ET_INTERN = "Intern"
ET_FULLTIME = "Full-time"
ET_CAN_HOP_DONG = (ET_PROBATION, ET_INTERN, ET_FULLTIME)
#: Goi y thoi han thu viec mac dinh khi thieu ngay ket thuc: ngay vao + 2 thang.
THANG_THU_VIEC_GOI_Y = 2


def as_date(v):
    if v in (None, ""):
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    return _dt.date.fromisoformat(str(v)[:10])


def add_months(d, n):
    """Cong n thang, giu ngay (31/01 + 1 thang -> 28/29/02)."""
    m = d.month - 1 + int(n)
    y = d.year + m // 12
    m = m % 12 + 1
    return _dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def ket_thuc_sau_thang(tu_ngay, so_thang):
    """Ngay ket thuc cua mot hop dong `so_thang` thang bat dau `tu_ngay` (tinh ca hai dau)."""
    return add_months(as_date(tu_ngay), so_thang) - _dt.timedelta(days=1)


def la_ngay_lam_viec(d, ngay_le=()):
    return d.weekday() < 5 and d not in ngay_le


def lui_ve_ngay_lam_viec(d, ngay_le=()):
    """Ngay lam viec GAN NHAT <= d (d la ngay lam viec thi giu nguyen)."""
    while not la_ngay_lam_viec(d, ngay_le):
        d -= _dt.timedelta(days=1)
    return d


def tien_toi_ngay_lam_viec(d, ngay_le=()):
    """Ngay lam viec GAN NHAT >= d."""
    while not la_ngay_lam_viec(d, ngay_le):
        d += _dt.timedelta(days=1)
    return d


def lui_ngay_lam_viec(d, so_ngay, ngay_le=()):
    """Ngay lam viec thu `so_ngay` TRUOC d (khong tinh chinh d)."""
    n = int(so_ngay or 0)
    while n > 0:
        d -= _dt.timedelta(days=1)
        if la_ngay_lam_viec(d, ngay_le):
            n -= 1
    return d


def cong_ngay_lam_viec(d, so_ngay, ngay_le=()):
    """Ngay lam viec thu `so_ngay` SAU d (khong tinh chinh d) - cung nghia voi
    approval_center.shared.workflow.ngay_lam_viec.cong_ngay_lam_viec, chep o day de domain nay
    khong phai import frappe."""
    n = int(so_ngay or 0)
    if n <= 0:
        return tien_toi_ngay_lam_viec(d, ngay_le)
    while n > 0:
        d += _dt.timedelta(days=1)
        if la_ngay_lam_viec(d, ngay_le):
            n -= 1
    return d


def la_hdld(row):
    return str((row or {}).get("loai_hop_dong") or "").startswith(HDLD_PREFIX)


def dong_hien_hanh(rows, hom_nay):
    """Dong hop dong DANG HIEU LUC hom nay: tu_ngay <= hom_nay, tu_ngay moi nhat.

    Dong chua co tu_ngay bi bo qua (khong biet bat dau khi nao thi khong noi duoc no dang chay).
    Khong co dong nao da bat dau -> None."""
    hom_nay = as_date(hom_nay)
    best = None
    for r in rows or []:
        tu = as_date(r.get("tu_ngay"))
        if not tu or tu > hom_nay:
            continue
        if best is None or tu > as_date(best.get("tu_ngay")):
            best = r
    return best


def loai_danh_gia(row):
    """Loai danh gia cho mot dong hop dong, hoac None neu dong do khong can danh gia
    (khong thoi han, hop dong dich vu, Khac)."""
    if not row:
        return None
    loai = row.get("loai_hop_dong") or ""
    if loai == THU_VIEC:
        return DG_THU_VIEC
    if loai == THUC_TAP:
        return DG_THUC_TAP
    if la_hdld(row) and not int(row.get("khong_thoi_han") or 0):
        return DG_HOP_DONG
    return None


def so_hd_xac_dinh_thoi_han(rows, tru_dong=None):
    """So HDLD xac dinh thoi han da ky (Dieu 20 BLLD 2019: chi duoc ky them MOT lan)."""
    return sum(1 for r in rows or []
               if la_hdld(r) and not int(r.get("khong_thoi_han") or 0)
               and (tru_dong is None or r.get("name") != tru_dong))


def hdld_tiep_theo(rows):
    """Nhan "HĐLĐ lần n" cho hop dong ke tiep (n = so dong HDLD da co + 1, toi da 5)."""
    n = sum(1 for r in rows or [] if la_hdld(r)) + 1
    return HDLD_PREFIX + str(min(n, HDLD_MAX))


def ngay_tao_nhap(loai, den_ngay, ngay_le=()):
    """Ngay he thong tao NHAP danh gia: D-21 (thu viec/thuc tap) / D-37 (hop dong), lui ve ngay
    lam viec - job chi chay ngay lam viec, nen moc roi vao T7/CN phai lam som hon, khong muon hon."""
    den = as_date(den_ngay)
    if not den or loai not in LICH_DANH_GIA:
        return None
    return lui_ve_ngay_lam_viec(den - _dt.timedelta(days=LICH_DANH_GIA[loai][0]), ngay_le)


def ngay_tu_gui(loai, den_ngay, ngay_le=()):
    """Ngay nhap tu GUI di: D-14 / D-30, lui ve ngay lam viec (cung ly do voi ngay_tao_nhap)."""
    den = as_date(den_ngay)
    if not den or loai not in LICH_DANH_GIA:
        return None
    return lui_ve_ngay_lam_viec(den - _dt.timedelta(days=LICH_DANH_GIA[loai][1]), ngay_le)


def thieu_ngay_ket_thuc(nv, rows, hom_nay):
    """Ly do ho so can C&B nhap / sua ngay ket thuc, hoac None neu du.

    nv: dict(employment_type, date_of_joining). Chi xet Probation / Intern / Full-time.
    Tra ve dict(ly_do, goi_y_den_ngay) - goi y chi co cho thu viec (ngay vao + 2 thang)."""
    et = (nv or {}).get("employment_type") or ""
    if et not in ET_CAN_HOP_DONG:
        return None
    hom_nay = as_date(hom_nay)
    row = dong_hien_hanh(rows, hom_nay)
    goi_y = None
    vao = as_date((nv or {}).get("date_of_joining"))
    if et == ET_PROBATION and vao:
        goi_y = ket_thuc_sau_thang(vao, THANG_THU_VIEC_GOI_Y)
    if not row:
        return {"ly_do": "Chưa có dòng hợp đồng hiện hành", "goi_y_den_ngay": goi_y, "dong": None}
    if int(row.get("khong_thoi_han") or 0):
        return None
    den = as_date(row.get("den_ngay"))
    if not den:
        if row.get("loai_hop_dong") == THU_VIEC and as_date(row.get("tu_ngay")):
            goi_y = ket_thuc_sau_thang(as_date(row.get("tu_ngay")), THANG_THU_VIEC_GOI_Y)
        return {"ly_do": "Dòng hợp đồng hiện hành thiếu ngày kết thúc", "goi_y_den_ngay": goi_y,
                "dong": row.get("name")}
    if den < hom_nay:
        return {"ly_do": "Hợp đồng hiện hành đã hết hạn, chưa có dòng mới", "goi_y_den_ngay": None,
                "dong": row.get("name")}
    return None

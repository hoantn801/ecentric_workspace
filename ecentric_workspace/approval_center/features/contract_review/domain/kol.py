# Copyright (c) 2026, eCentric and contributors
"""Hop dong KOL/KOC tren Contract Review (form 27) - quy tac thuan, khong goi frappe.

Chot voi anh Hoan 11/11/2026 (plan "Hop dong KOL/KOC len ERP"):
  * Loai hop dong KOL_CONTRACT_TYPE; mau EC hay mau creator la `request_type` co san
    ("Template from EC" / "Template from partner").
  * Thue: ca nhan khau tru TNCN 10%, cong ty cong VAT 8%, ho kinh doanh tu chiu thue. Ty le
    sua duoc tung phieu (vd khoan duoi 2 trieu khong khau tru).
  * Thanh toan sau nghiem thu, hoac coc truoc (% coc). Han thanh toan = ngay BBNT hoan tat +
    so ngay (ngay LICH), roi vao T7/CN thi doi sang thu Hai.
  * So hop dong: ddmmyyyy/HDDV/ECENTRIC-<ma doi tac>.<ma brand> (khuon dang cua sheet cu).
  * Tong hop dong vuot doanh thu EC cua SO: CANH BAO, khong chan.
  * Hoa hong affiliate cung di luong nay: mot hop dong nhan nhieu dot BBNT / nhieu DNTT.
"""
import datetime as _dt
import math
from decimal import ROUND_HALF_UP, Decimal

from ecentric_workspace.approval_center.features.contract_review.domain.vn_words import amount_in_words

KOL_CONTRACT_TYPE = "KOL/KOC / Creator (EC)"
TEMPLATE_EC = "Template from EC / Mẫu theo khung EC"
TEMPLATE_PARTNER = "Template from partner / Mẫu theo khung đối tác"

SERVICE_TYPES = ("Livestream", "Video", "Livestream + Video", "Hoa hồng affiliate")
PLATFORMS = ("TikTok", "Shopee", "Facebook", "Khác")

# Kieu nhap so tien - dung 5 kieu sheet cu dang dung (296 booking, do 11/11).
NET_AFTER_PIT = "Thực nhận sau TNCN"
GROSS_BEFORE_PIT = "Gross trước TNCN"
BEFORE_VAT = "Chưa VAT"
WITH_VAT = "Đã VAT"
HOUSEHOLD_TOTAL = "Tổng đã gồm thuế HKD"
AMOUNT_TYPES = (NET_AFTER_PIT, GROSS_BEFORE_PIT, BEFORE_VAT, WITH_VAT, HOUSEHOLD_TOTAL)
AMOUNT_TYPES_BY_CREATOR = {
    "Cá nhân": (NET_AFTER_PIT, GROSS_BEFORE_PIT),
    "Công ty": (BEFORE_VAT, WITH_VAT),
    "Hộ kinh doanh": (HOUSEHOLD_TOTAL,),
}
DEFAULT_PIT_RATE = 10.0
DEFAULT_VAT_RATE = 8.0

PAY_AFTER_ACCEPTANCE = "Thanh toán sau nghiệm thu"
PAY_ADVANCE = "Cọc trước"
PAYMENT_SCHEDULES = (PAY_AFTER_ACCEPTANCE, PAY_ADVANCE)
ADVANCE_PERCENTS = (20, 30, 40, 50)
DEFAULT_PAYMENT_DAYS = 30

# Trang thai ky (tam thoi ky tren cong roi tai ban da ky; giai doan 4 thay bang SCTS).
SIGN_PENDING = "Chưa ký"
SIGN_DONE = "Đã ký đủ"

# Trang thai mot dot nghiem thu (BBNT).
BBNT_DRAFT = "Nháp"
BBNT_SENT = "Đã gửi ký"
BBNT_DONE = "Hoàn tất"
BBNT_STATUSES = (BBNT_DRAFT, BBNT_SENT, BBNT_DONE)


def is_kol(doc):
    return (doc.get("contract_type") or "") == KOL_CONTRACT_TYPE


def _f(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _num(value, label):
    """So nguoi dung nhap: rong = 0; chu / inf / nan -> ValueError (khong am tham thanh 0)."""
    if value in (None, ""):
        return 0.0
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s không phải là số." % label)
    if math.isnan(out) or math.isinf(out):
        raise ValueError("%s không hợp lệ." % label)
    return out


def _r(value):
    """Lam tron toi dong, nua len (0,5 -> 1) - round() cua Python lam tron chan (banker's)."""
    return float(Decimal(repr(float(value))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# Gioi han thue suat: TNCN luy tien cao nhat 35%, VAT cao nhat 10%. Ngoai khoang = go nham.
PIT_RATE_RANGE = (0.0, 35.0)
VAT_RATE_RANGE = (0.0, 10.0)
MAX_AMOUNT = 1e12


def _rate(value, default, bounds, label):
    rate = default if value in (None, "") else _num(value, label)
    if not bounds[0] <= rate <= bounds[1]:
        raise ValueError("%s phải từ %g%% đến %g%%." % (label, bounds[0], bounds[1]))
    return rate


def compute_amounts(creator_type, amount_type, amount_input, pit_rate=None, vat_rate=None):
    """Quy doi so tien nhap ve cac con so ghi tren hop dong va DNTT.

    -> dict(gross, pit, vat, payable, contract_value), deu lam tron toi dong:
      gross          = gia tri dich vu truoc thue (truoc TNCN / truoc VAT)
      pit            = TNCN eCentric khau tru va nop thay (ca nhan)
      vat            = VAT cong ty xuat hoa don
      payable        = so tien chuyen cho creator
      contract_value = chi phi eCentric chiu = gross + vat (ca nhan: gross)
    Kieu nhap khong hop voi loai creator -> ValueError (khong doan).
    """
    if amount_type not in AMOUNT_TYPES_BY_CREATOR.get(creator_type, ()):
        raise ValueError("Kiểu nhập tiền '%s' không dùng cho creator %s." % (amount_type, creator_type))
    amount = _num(amount_input, "Số tiền")
    if amount <= 0:
        raise ValueError("Số tiền phải lớn hơn 0.")
    if amount > MAX_AMOUNT:
        raise ValueError("Số tiền quá lớn, kiểm tra lại.")
    # Chi kiem thue suat DUNG TOI: ca nhan khong xet VAT, cong ty khong xet TNCN (o kia co the con
    # gia tri cu ngoai khoang tu luc doi loai creator).
    uses_pit = amount_type in (NET_AFTER_PIT, GROSS_BEFORE_PIT)
    uses_vat = amount_type in (BEFORE_VAT, WITH_VAT)
    pit_rate = _rate(pit_rate, DEFAULT_PIT_RATE, PIT_RATE_RANGE, "Thuế TNCN") if uses_pit else 0.0
    vat_rate = _rate(vat_rate, DEFAULT_VAT_RATE, VAT_RATE_RANGE, "VAT") if uses_vat else 0.0
    pit = vat = 0.0
    if amount_type == NET_AFTER_PIT:
        gross = _r(amount / (1 - pit_rate / 100.0))
        pit = gross - _r(amount)
        payable = _r(amount)
    elif amount_type == GROSS_BEFORE_PIT:
        gross = _r(amount)
        pit = _r(gross * pit_rate / 100.0)
        payable = gross - pit
    elif amount_type == BEFORE_VAT:
        gross = _r(amount)
        vat = _r(gross * vat_rate / 100.0)
        payable = gross + vat
    elif amount_type == WITH_VAT:
        payable = _r(amount)
        gross = _r(payable / (1 + vat_rate / 100.0))
        vat = payable - gross
    else:  # HOUSEHOLD_TOTAL
        gross = payable = _r(amount)
    if payable < 1:
        raise ValueError("Số tiền phải lớn hơn 0.")
    return {"gross": float(gross), "pit": float(pit), "vat": float(vat),
            "payable": float(payable), "contract_value": float(gross + vat)}


def advance_amount(payable, schedule, percent):
    if schedule != PAY_ADVANCE:
        return 0.0
    pct = _num(percent, "Tỷ lệ cọc")
    if pct not in ADVANCE_PERCENTS:
        raise ValueError("Tỷ lệ cọc phải là %s%%." % "/".join(str(p) for p in ADVANCE_PERCENTS))
    return _r(_f(payable) * pct / 100.0)


def payment_days(days):
    """So ngay thanh toan sau BBNT: rong = mac dinh 30; 0 = trong ngay; am -> ValueError."""
    if days in (None, ""):
        return DEFAULT_PAYMENT_DAYS
    try:
        out = int(float(days))
    except (TypeError, ValueError):
        raise ValueError("Số ngày thanh toán không phải là số.")
    if out < 0 or out > 365:
        raise ValueError("Số ngày thanh toán phải từ 0 đến 365.")
    return out


def due_date(acceptance_date, days):
    """Han thanh toan = ngay BBNT hoan tat + `days` ngay lich; T7/CN doi sang thu Hai."""
    if not acceptance_date:
        return None
    if isinstance(acceptance_date, str):
        acceptance_date = _dt.date.fromisoformat(acceptance_date[:10])
    if isinstance(acceptance_date, _dt.datetime):
        acceptance_date = acceptance_date.date()
    d = acceptance_date + _dt.timedelta(days=payment_days(days))
    while d.weekday() >= 5:
        d += _dt.timedelta(days=1)
    return d


def number_base(sign_date, party_code, brand_code):
    return contract_number(sign_date, party_code, brand_code, ())


def number_fits(number, base):
    """So hop dong hien co van dung voi ngay ky / doi tac / brand hien tai (ke ca hau to -n)?"""
    if not number:
        return False
    if number == base:
        return True
    head, _sep, tail = number.rpartition("-")
    return head == base and tail.isdigit()


def contract_number(sign_date, party_code, brand_code, existing=()):
    """ddmmyyyy/HDDV/ECENTRIC-<doi tac>.<brand>; trung thi them -2, -3...

    Thieu ma doi tac hoac ma brand -> ValueError: so hop dong sai di vao van ban phap ly va
    lech voi so ke toan, nen khong tu bia."""
    party = (party_code or "").strip().upper()
    brand = (brand_code or "").strip().upper()
    if not party:
        raise ValueError("Creator chưa có mã viết tắt trong số hợp đồng.")
    if not brand:
        raise ValueError("Brand chưa có mã brand (Brand code).")
    if isinstance(sign_date, str):
        sign_date = _dt.date.fromisoformat(sign_date[:10])
    base = "%s/HDDV/ECENTRIC-%s.%s" % (sign_date.strftime("%d%m%Y"), party, brand)
    taken = set(existing or ())
    if base not in taken:
        return base
    n = 2
    while "%s-%d" % (base, n) in taken:
        n += 1
    return "%s-%d" % (base, n)


def revenue_warning(so_revenue, other_contracts_total, this_value):
    """Chuoi canh bao (rong = khong vuot). Chi CANH BAO - anh Hoan chot 11/11."""
    revenue = _f(so_revenue)
    total = _f(other_contracts_total) + _f(this_value)
    if revenue <= 0:
        return "SO chưa có doanh thu EC để đối chiếu."
    if total > revenue + 0.5:
        return ("Tổng hợp đồng KOL/KOC trên SO này %s vượt doanh thu EC %s (vượt %s)."
                % (fmt_money(total), fmt_money(revenue), fmt_money(total - revenue)))
    return ""


def fmt_money(value):
    return "{:,.0f}".format(_f(value)).replace(",", ".")


def acceptance_cap(signed, advance, done_rows_amount, contract_payable):
    """So tien toi da duoc dua vao DNTT luc nay (truoc khi tru phan da de nghi).

    Chot 11/11: coc chi chi khi creator DA KY; phan con lai chi chi theo BBNT da hoan tat.
    Khong bao gio vuot tong so tien phai tra cua hop dong."""
    if not signed:
        return 0.0
    cap = _f(advance) + _f(done_rows_amount)
    payable = _f(contract_payable)
    return min(cap, payable) if payable else cap


def validate_kol(doc, creator_type):
    """Loi nhap lieu cua phieu KOL truoc khi gui -> danh sach thong bao."""
    errors = []
    if not doc.get("sales_order"):
        errors.append("Chọn SO cung cấp dịch vụ cho brand trước khi gửi hợp đồng.")
    if not doc.get("creator"):
        errors.append("Chọn creator.")
    if doc.get("service_type") not in SERVICE_TYPES:
        errors.append("Chọn loại dịch vụ.")
    if doc.get("payment_schedule") not in PAYMENT_SCHEDULES:
        errors.append("Chọn hình thức thanh toán.")
    if creator_type and doc.get("amount_type") not in AMOUNT_TYPES_BY_CREATOR.get(creator_type, ()):
        errors.append("Kiểu nhập tiền không hợp với loại creator %s." % creator_type)
    if doc.get("request_type") not in (TEMPLATE_EC, TEMPLATE_PARTNER):
        errors.append("Hợp đồng KOL/KOC chỉ dùng mẫu EC hoặc mẫu của creator.")
    return errors


def placeholders(doc, creator, brand_code="", so_label=""):
    """Bang {{ten}} -> gia tri de dien mau. Mot noi duy nhat dinh nghia ten placeholder.

    `creator` la ban ghi day du (co PII): chi goi tu server luc tao tep, khong tra ra client."""
    def money(v):
        return fmt_money(v) if v not in (None, "") else ""

    def day(v):
        if not v:
            return ""
        if isinstance(v, str):
            v = _dt.date.fromisoformat(v[:10])
        return v.strftime("%d/%m/%Y")

    payable = doc.get("payable_amount")
    return {
        "so_hop_dong": doc.get("contract_no") or "",
        "ngay_ky": day(doc.get("contract_date")),
        "brand": doc.get("brand") or "",
        "ma_brand": brand_code or "",
        "so": so_label or doc.get("sales_order") or "",
        "dich_vu": doc.get("service_type") or "",
        "nen_tang": doc.get("platform") or "",
        "so_luong": str(doc.get("quantity") or ""),
        "thoi_luong": doc.get("duration") or "",
        "ngay_thuc_hien": doc.get("air_dates") or "",
        "ngay_bat_dau": day(doc.get("contract_start_date")),
        "ngay_ket_thuc": day(doc.get("contract_end_date")),
        "ten_creator": creator.get("supplier_name") or "",
        "loai_creator": creator.get("ec_cr_type") or "",
        "cccd": creator.get("ec_cr_cccd") or "",
        "ngay_cap": day(creator.get("ec_cr_cccd_issue_date")),
        "noi_cap": creator.get("ec_cr_cccd_issue_place") or "",
        "ngay_sinh": day(creator.get("ec_cr_dob")),
        "dia_chi": creator.get("ec_cr_address") or "",
        "mst": creator.get("tax_id") or "",
        "dien_thoai": creator.get("ec_phone") or "",
        "email": creator.get("ec_cr_email") or "",
        "nguoi_dai_dien": creator.get("ec_cr_representative_name") or "",
        "chuc_vu": creator.get("ec_cr_representative_title") or "",
        "tiktok_id": creator.get("ec_cr_tiktok_id") or "",
        "link_kenh": creator.get("ec_cr_channel_url") or creator.get("ec_cr_shopee_url") or "",
        "shopee_id": creator.get("ec_cr_shopee_id") or "",
        "chu_tai_khoan": creator.get("ec_cr_account_holder") or creator.get("supplier_name") or "",
        "so_tai_khoan": creator.get("ec_bank_account_no") or "",
        "ngan_hang": creator.get("ec_bank_name") or "",
        "chi_nhanh": creator.get("ec_cr_bank_branch") or "",
        "gia_tri_truoc_thue": money(doc.get("gross_amount")),
        "thue_tncn": money(doc.get("pit_amount")),
        "thue_suat_tncn": "%g%%" % (DEFAULT_PIT_RATE if doc.get("pit_rate") in (None, "") else _f(doc.get("pit_rate"))),
        "vat": money(doc.get("vat_amount")),
        "thue_suat_vat": "%g%%" % (DEFAULT_VAT_RATE if doc.get("vat_rate") in (None, "") else _f(doc.get("vat_rate"))),
        "so_tien_thanh_toan": money(payable),
        "so_tien_bang_chu": amount_in_words(payable) if payable else "",
        "gia_tri_hop_dong": money(doc.get("contract_value")),
        "gia_tri_bang_chu": amount_in_words(doc.get("contract_value")) if doc.get("contract_value") else "",
        "hinh_thuc_thanh_toan": doc.get("payment_schedule") or "",
        "ty_le_coc": ("%g%%" % _f(doc.get("advance_percent"))) if doc.get("advance_percent") else "",
        "tien_coc": money(doc.get("advance_amount")),
        "tien_coc_bang_chu": amount_in_words(doc.get("advance_amount")) if doc.get("advance_amount") else "",
        "so_ngay_thanh_toan": str(payment_days(doc.get("payment_term_days"))),
        "ty_le_hoa_hong": ("%g%%" % _f(doc.get("commission_rate"))) if doc.get("commission_rate") else "",
    }


# Placeholder chi co o BBNT (mau hop dong dung toi = mau sai, bao khi luu mau).
BBNT_ONLY_PLACEHOLDERS = ("dot_nghiem_thu", "noi_dung_nghiem_thu", "ngay_nghiem_thu",
                          "so_tien_nghiem_thu", "so_tien_nghiem_thu_bang_chu")
# Mau DUNG toi ma gia tri RONG = hop dong co cho trong -> bao thieu, khong cho gui.
# Truong tuy chon (TikTok/Shopee ID, email, hoa hong, coc...) rong la binh thuong.
REQUIRED_WHEN_USED = {
    "_all": ("so_hop_dong", "ngay_ky", "ten_creator", "dia_chi", "so_tai_khoan", "ngan_hang",
             "chu_tai_khoan", "dich_vu", "so_tien_thanh_toan", "so_tien_bang_chu",
             "gia_tri_hop_dong", "gia_tri_truoc_thue", "brand", "ma_brand"),
    "Cá nhân": ("cccd", "ngay_cap", "noi_cap"),
    "Công ty": ("mst", "nguoi_dai_dien", "chuc_vu"),
    "Hộ kinh doanh": ("mst",),
}


def empty_required(values, used, creator_type):
    """Placeholder mau co dung ma gia tri dang rong (va bat buoc voi loai creator nay)."""
    need = set(REQUIRED_WHEN_USED["_all"]) | set(REQUIRED_WHEN_USED.get(creator_type, ()))
    return [k for k in used if k in need and not str(values.get(k) or "").strip()]


def known_placeholders(kind_is_bbnt):
    keys = set(PLACEHOLDER_HELP)
    return keys if kind_is_bbnt else keys - set(BBNT_ONLY_PLACEHOLDERS)


def acceptance_placeholders(doc, creator, row, brand_code="", so_label=""):
    """Placeholder cua BBNT = cua hop dong + thong tin dot nghiem thu."""
    values = placeholders(doc, creator, brand_code, so_label)
    amount = row.get("amount")
    values.update({
        "dot_nghiem_thu": str(row.get("idx") or ""),
        "noi_dung_nghiem_thu": row.get("description") or "",
        "ngay_nghiem_thu": values_day(row.get("acceptance_date")),
        "so_tien_nghiem_thu": fmt_money(amount) if amount else "",
        "so_tien_nghiem_thu_bang_chu": amount_in_words(amount) if amount else "",
    })
    return values


def values_day(v):
    if not v:
        return ""
    if isinstance(v, str):
        v = _dt.date.fromisoformat(v[:10])
    return v.strftime("%d/%m/%Y")


PLACEHOLDER_HELP = sorted(acceptance_placeholders({}, {}, {}).keys())

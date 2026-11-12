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

Chot them 12/11/2026 (dung lai 18 mau + logic tool Google Sheet cu cua Ke toan):
  * So ngay thanh toan mac dinh theo tool cu: ca nhan 35, cong ty 30, ho kinh doanh 30,
    Shopee 15 (BBNT) - sua duoc tung phieu.
  * Coc: cong ty tinh tren gia tri TRUOC VAT, ca nhan tren so thuc nhan; ho kinh doanh khong coc;
    Shopee chi co mau Cong ty - Livestream, chua co mau coc.
  * Ngay trong so hop dong = ngay thuc hien DAU TIEN (khong phai ngay ky).
  * Tong hop dong vuot doanh thu EC cua SO: CANH BAO, khong chan.
  * Hoa hong affiliate cung di luong nay: mot hop dong nhan nhieu dot BBNT / nhieu DNTT.
"""
import datetime as _dt
import math
import re
from decimal import ROUND_HALF_UP, Decimal


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
DEFAULT_ADVANCE_PERCENT = 40
DEFAULT_PAYMENT_DAYS = 30
PAYMENT_DAYS_BY_CREATOR = {"Cá nhân": 35, "Công ty": 30, "Hộ kinh doanh": 30}
SHOPEE = "Shopee"
SHOPEE_BBNT_PAYMENT_DAYS = 15     # CONFIG PAYMENT_DAYS_COMPANY_SHOPEE_BBNT cua tool cu
SHOPEE_HDDV_PAYMENT_DAYS = 30     # CONFIG PAYMENT_DAYS_COMPANY_SHOPEE_HDDV

# Trang thai ky (tam thoi ky tren cong roi tai ban da ky; giai doan 4 thay bang SCTS).
SIGN_PENDING = "Chưa ký"
SIGN_REVIEW = "Chờ kiểm tra"
SIGN_DONE = "Đã ký đủ"
AUTO_VERIFIER = "Tự động (máy kiểm)"
# Hop dong / BBNT ky du = it nhat 2 chu ky so (eCentric + creator).
MIN_SIGNATURES = 2

# Trang thai mot dot nghiem thu (BBNT).
BBNT_DRAFT = "Nháp"
BBNT_SENT = "Đã gửi ký"
BBNT_REVIEW = "Chờ kiểm tra"
BBNT_DONE = "Hoàn tất"
BBNT_STATUSES = (BBNT_DRAFT, BBNT_SENT, BBNT_REVIEW, BBNT_DONE)


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
    # Nhan voi TY LE THAP PHAN (0.1, 0.08) nhu calculateMoney_ cua tool cu - (x*8)/100 va x*0.08
    # lech nhau o so .5 khi lam tron, hop dong ERP phai ra dung so cua tool cu.
    pr, vr = pit_rate / 100.0, vat_rate / 100.0
    if amount_type == NET_AFTER_PIT:
        payable = _r(amount)                 # tool cu lam tron so thuc nhan TRUOC roi moi quy ra gross
        gross = _r(payable / (1 - pr))
        pit = gross - payable
    elif amount_type == GROSS_BEFORE_PIT:
        gross = _r(amount)
        pit = _r(gross * pr)
        payable = gross - pit
    elif amount_type == BEFORE_VAT:
        gross = _r(amount)
        vat = _r(gross * vr)
        payable = gross + vat
    elif amount_type == WITH_VAT:
        payable = _r(amount)
        gross = _r(payable / (1 + vr))
        vat = payable - gross
    else:  # HOUSEHOLD_TOTAL
        gross = payable = _r(amount)
    if payable < 1:
        raise ValueError("Số tiền phải lớn hơn 0.")
    return {"gross": float(gross), "pit": float(pit), "vat": float(vat),
            "payable": float(payable), "contract_value": float(gross + vat)}


def advance_amount(amounts, creator_type, schedule, percent):
    """Tien coc theo tool cu: cong ty = % gia tri TRUOC VAT (VAT nam o phan con lai);
    ca nhan = % so THUC NHAN sau TNCN; ho kinh doanh khong coc."""
    if schedule != PAY_ADVANCE:
        return 0.0
    if creator_type == "Hộ kinh doanh":
        raise ValueError("Hộ kinh doanh chỉ thanh toán 100% sau nghiệm thu và hóa đơn hợp lệ, không cọc.")
    pct = _num(percent, "Tỷ lệ cọc")
    if pct not in ADVANCE_PERCENTS:
        raise ValueError("Tỷ lệ cọc phải là %s%%." % "/".join(str(p) for p in ADVANCE_PERCENTS))
    base = (amounts or {}).get("gross") if creator_type == "Công ty" else (amounts or {}).get("payable")
    return _r(_f(base) * (pct / 100.0))


def default_payment_days(creator_type, platform=None):
    # Tool cu: 15 ngay chi co o mau Cong ty - Shopee (PAYMENT_DAYS_COMPANY_SHOPEE_BBNT).
    if platform == SHOPEE and creator_type == "Công ty":
        return SHOPEE_BBNT_PAYMENT_DAYS
    return PAYMENT_DAYS_BY_CREATOR.get(creator_type, DEFAULT_PAYMENT_DAYS)


def payment_days(days, creator_type=None, platform=None):
    """So ngay thanh toan sau BBNT: rong = mac dinh theo loai creator; 0 = trong ngay; am -> loi."""
    if days in (None, ""):
        return default_payment_days(creator_type, platform)
    try:
        out = int(float(days))
    except (TypeError, ValueError):
        raise ValueError("Số ngày thanh toán không phải là số.")
    if out < 0 or out > 365:
        raise ValueError("Số ngày thanh toán phải từ 0 đến 365.")
    return out


def due_date(acceptance_date, days, creator_type=None, platform=None, holidays=()):
    """Han thanh toan = ngay BBNT hoan tat + `days` ngay lich; roi vao T7/CN hoac ngay le
    (Holiday List cong ty) thi doi sang ngay lam viec lien sau (PO 12/11)."""
    if not acceptance_date:
        return None
    if isinstance(acceptance_date, str):
        acceptance_date = _dt.date.fromisoformat(acceptance_date[:10])
    if isinstance(acceptance_date, _dt.datetime):
        acceptance_date = acceptance_date.date()
    d = acceptance_date + _dt.timedelta(days=payment_days(days, creator_type, platform))
    off = set(holidays or ())
    while d.weekday() >= 5 or d in off:
        d += _dt.timedelta(days=1)
    return d


def number_base(number_date, party_code, brand_code):
    return contract_number(number_date, party_code, brand_code, ())


def number_fits(number, base):
    """So hop dong hien co van dung voi ngay ky / doi tac / brand hien tai (ke ca hau to -n)?"""
    if not number:
        return False
    if number == base:
        return True
    head, _sep, tail = number.rpartition("-")
    return head == base and tail.isdigit()


def contract_number(number_date, party_code, brand_code, existing=()):
    """ddmmyyyy/HDDV/ECENTRIC-<doi tac>.<brand>; trung thi them -2, -3...

    `number_date` = ngay thuc hien DAU TIEN (tool cu: formatDate_(firstServiceDate, 'ddMMyyyy')).

    Thieu ma doi tac hoac ma brand -> ValueError: so hop dong sai di vao van ban phap ly va
    lech voi so ke toan, nen khong tu bia."""
    party = (party_code or "").strip().upper()
    brand = (brand_code or "").strip().upper()
    if not party:
        raise ValueError("Creator chưa có mã viết tắt trong số hợp đồng.")
    if not brand:
        raise ValueError("Brand chưa có mã brand (Brand code).")
    if isinstance(number_date, str):
        number_date = _dt.date.fromisoformat(number_date[:10])
    base = "%s/HDDV/ECENTRIC-%s.%s" % (number_date.strftime("%d%m%Y"), party, brand)
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


def validate_kol(doc, creator_type, today=None):
    """Loi nhap lieu cua phieu KOL truoc khi gui -> danh sach thong bao."""
    errors = []
    # SO KHONG chon tren hop dong (anh Hoan 12/11: SO gan o DNTT de ke toan doi chieu doanh thu).
    if not doc.get("brand"):
        errors.append("Chọn brand (mã brand nằm trong số hợp đồng).")
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
    if creator_type == "Hộ kinh doanh" and doc.get("payment_schedule") == PAY_ADVANCE:
        errors.append("Hộ kinh doanh chỉ thanh toán sau nghiệm thu, không cọc.")
    if doc.get("request_type") == TEMPLATE_EC:
        errors.extend(ec_template_errors(doc, creator_type, today))
    return errors


EC_TEMPLATE_PLATFORMS = ("TikTok", SHOPEE)
AFFILIATE = "Hoa hồng affiliate"


def ec_template_errors(doc, creator_type, today=None):
    """Gioi han cua bo mau EC (giong resolveTemplateId_ cua tool cu)."""
    errors = []
    if doc.get("platform") and doc.get("platform") not in EC_TEMPLATE_PLATFORMS:
        errors.append("Mẫu EC chỉ viết cho TikTok và Shopee. Nền tảng %s: dùng mẫu của creator."
                      % doc.get("platform"))
    if doc.get("platform") == SHOPEE:
        if creator_type != "Công ty" or doc.get("service_type") != "Livestream":
            errors.append("Shopee hiện chỉ có mẫu Công ty - Livestream.")
        if doc.get("payment_schedule") == PAY_ADVANCE:
            errors.append("Mẫu Shopee chưa hỗ trợ cọc trước.")
    try:
        # Hoa hong affiliate tinh theo ky, khong bat buoc ngay buoi live (so HD lay ngay ky).
        if not service_dates(doc, today) and doc.get("service_type") != AFFILIATE:
            errors.append("Nhập ngày thực hiện / ngày air (vd 05/12 hoặc 05,06/12/2026).")
    except ValueError as e:
        errors.append(str(e))
    return errors


def service_dates(doc, today=None):
    """Ngay thuc hien doc tu o 'air_dates'. Khong ghi nam = lan sap toi tinh tu `today` (ngay cua
    site) - KHONG doan theo ngay ky (ngay ky tu lui ve truoc buoi dau, doan theo no thi troi nam)."""
    from ecentric_workspace.approval_center.features.contract_review.domain.kol_texts import (
        parse_service_dates)
    if isinstance(today, str):
        today = _dt.date.fromisoformat(today[:10])
    return parse_service_dates(doc.get("air_dates"), today or _dt.date.today())


def count_signatures(pdf_bytes):
    """So chu ky so trong PDF: moi chu ky co mot tu dien /ByteRange (PAdES / chuan Adobe)."""
    return len(re.findall(rb"/ByteRange\s*\[", bytes(pdf_bytes or b"")))


def signed_pdf_findings(pdf_bytes, text_tokens, text, contract_no, amount=None,
                        min_signatures=MIN_SIGNATURES):
    """May kiem ban da ky (anh Hoan 11/11: 'can ke toan hoac AI check'). Rong = dat, tu xac
    nhan; co dong nao thi chuyen Ke toan xem.

      * dung la PDF;
      * co >= 2 chu ky so (eCentric + creator) - ban scan ky tay se khong co -> Ke toan xem;
      * co so hop dong trong van ban (dung hop dong nay, khong phai tep khac);
      * BBNT: co so tien cua dot.
    Chu ky so khong doc duoc bang mat / AI nen dem bang may, khong hoi AI."""
    data = bytes(pdf_bytes or b"")
    out = []
    if not data.startswith(b"%PDF"):
        return ["Tệp không phải PDF."]
    n = count_signatures(data)
    if n < min_signatures:
        out.append("Tìm thấy %d chữ ký số, cần ít nhất %d (eCentric + creator). Bản scan ký tay "
                   "thì Kế toán xem và xác nhận." % (n, min_signatures))
    flat = " ".join((text or "").split()).lower()
    if not text:
        out.append("Không đọc được chữ trong tệp (PDF dạng ảnh).")
    elif contract_no and contract_no.lower() not in flat:
        out.append("Không thấy số hợp đồng %s trong tệp." % contract_no)
    if amount and text:
        digits = str(int(round(_f(amount))))
        if digits not in (text_tokens or set()):
            out.append("Không thấy số tiền %s trong tệp." % fmt_money(amount))
    return out

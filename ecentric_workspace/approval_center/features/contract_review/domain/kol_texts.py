# Copyright (c) 2026, eCentric and contributors
"""Ngay ky, ma doi tac va cac doan van dien vao mau HDDV/BBNT - PORT tu tool Google Sheet cu.

Nguon: Apps Script "TOOL TAO HDDV & BBNT - ECENTRIC" ban 2026.10.05-PERFORMANCE-V5.0.3
(ham buildWorkTexts_, buildAdvanceServiceTexts_, businessDateBefore_/After_, parseServiceDates_,
resolvePartyCode_, companyCode_, initials_, combineBankBranch_, normalizeVietnamAddress_).
Anh Hoan chot 12/11: 18 mau Google Docs cua Ke toan dung lai nguyen ven tren ERP, nen chu
trong hop dong phai ra GIONG HET tool cu - sua cau chu o day la sua van ban phap ly.

Thuan Python, khong goi frappe.
"""
import datetime as _dt
import re
import unicodedata

LIVESTREAM, VIDEO, HYBRID = "LIVESTREAM", "VIDEO", "HYBRID"
SHOPEE = "Shopee"


def service_kind(service_type):
    """Loai dich vu ERP -> khoa tool cu. Hoa hong affiliate di cung van ban livestream."""
    s = (service_type or "").lower()
    if "video" in s and "live" in s:
        return HYBRID
    if "video" in s:
        return VIDEO
    return LIVESTREAM


def strip_accents(text):
    text = unicodedata.normalize("NFD", str(text or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D")


# ---------------------------------------------------------------- ngay thuc hien
_SHORTHAND = re.compile(r"^(\d{1,2}(?:\s*,\s*\d{1,2})+)\s*[/.-]\s*(\d{1,2})(?:\s*[/.-]\s*(\d{2,4}))?$")
_ONE = re.compile(r"^(\d{1,2})\s*[/.-]\s*(\d{1,2})(?:\s*[/.-]\s*(\d{2,4}))?$")
_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
# "05-06/12", "05 - 10/12": khoang ngay (rat hay go) - khong doan, bao ro cach viet.
_RANGE = re.compile(r"(?<![\d/.-])\d{1,2}\s*[-–]\s*\d{1,2}\s*[/.]\s*\d{1,2}(?![\d-])")


def _year(y):
    y = int(y)
    return 2000 + y if y < 100 else y


def _make(year, month, day, raw):
    try:
        return _dt.date(int(year), int(month), int(day))
    except ValueError:
        raise ValueError("Ngày thực hiện '%s' không hợp lệ." % raw)


# Ngay khong ghi nam: lay lan GAN NHAT SAP TOI tinh tu hom nay (cho lui toi da 60 ngay - booking
# nhap bu sau khi da live). Tool cu dung nam co dinh trong CONFIG nen thang 12 nhap "05/01" ra
# ngay da qua; doan theo ngay ky thi ngay ky lui sang nam truoc keo ca ngay thuc hien troi theo.
PAST_GRACE_DAYS = 60
YEAR_RANGE = 2                      # chi nhan nam trong [nam nay - 1, nam nay + 2]


def _guess(month, day, today, raw, after=None):
    """Nam cho ngay khong ghi nam. `after` = ngay lien truoc trong danh sach: '28/12, 02/01'
    thi 02/01 sang nam sau."""
    for year in (today.year - 1, today.year, today.year + 1, today.year + 2):
        try:
            d = _dt.date(year, int(month), int(day))
        except ValueError:
            continue
        if d >= today - _dt.timedelta(days=PAST_GRACE_DAYS) and (after is None or d >= after):
            return d
    raise ValueError("Ngày thực hiện '%s' không hợp lệ." % raw)


def _check_year(d, today, raw):
    if not (today.year - 1 <= d.year <= today.year + YEAR_RANGE):
        raise ValueError("Năm của ngày thực hiện '%s' không hợp lý (%d). Ghi đủ 4 số, vd 05/12/%d."
                         % (raw, d.year, today.year))
    return d


def parse_service_dates(text, today):
    """'05,06/12' | '05/12, 12/12/2026' | '2026-12-05' -> list date da sap xep (rong -> []).

    `today` = ngay hien tai cua site (date). Ngay ghi du nam thi giu nguyen (kiem nam hop ly);
    ngay khong ghi nam thi doan lan sap toi (xem _guess)."""
    raw = re.sub(r"\s+", " ", str(text or "").strip())
    if not raw:
        return []
    if _RANGE.search(raw):
        raise ValueError("'%s' là khoảng ngày: ghi từng ngày, cách nhau dấu phẩy (vd 05,06/12 hoặc "
                         "05/12, 06/12)." % raw)
    m = _SHORTHAND.match(raw)
    if m:
        days = [d.strip() for d in m.group(1).split(",")]
        if m.group(3):
            year = _year(m.group(3))
            return sorted(_check_year(_make(year, m.group(2), d, raw), today, raw) for d in days)
        out, prev = [], None
        for d in days:
            prev = _guess(m.group(2), d, today, raw, prev)
            out.append(prev)
        return sorted(out)
    parts = [p.strip() for p in re.split(r"[;,\n]+", raw) if p.strip()]
    # Co ngay ghi du nam ("12/12/2026; 05/12") thi ngay khong ghi nam lay CUNG nam do - nguoi go
    # khong nhat thiet theo thu tu thoi gian.
    explicit = None
    for part in parts:
        iso, one = _ISO.match(part), _ONE.match(part)
        if iso or (one and one.group(3)):
            explicit = int(iso.group(1)) if iso else _year(one.group(3))
            break
    out, prev = [], None
    for part in parts:
        iso, one = _ISO.match(part), _ONE.match(part)
        if iso:
            d = _check_year(_make(iso.group(1), iso.group(2), iso.group(3), part), today, part)
        elif one and one.group(3):
            d = _check_year(_make(_year(one.group(3)), one.group(2), one.group(1), part), today, part)
        elif one and explicit:
            d = _check_year(_make(explicit, one.group(2), one.group(1), part), today, part)
        elif one:
            d = _guess(one.group(2), one.group(1), today, part, prev)
        else:
            raise ValueError("Không đọc được ngày thực hiện '%s' (vd 05/12 hoặc 05,06/12/2026). "
                             "Nhiều ngày thì cách nhau bằng dấu phẩy, không dùng dấu gạch." % part)
        prev = d
        out.append(d)
    return sorted(out)


def _business(d, step, holidays):
    while d.weekday() >= 5 or d in holidays:
        d += _dt.timedelta(days=step)
    return d


def business_day_before(chosen, boundary, holidays=(), days=1):
    """Ngay ky HDDV: ngay nguoi dung chon (neu truoc ngay thuc hien dau) hoac boundary - 1, lui ve
    ngay lam viec (bo T7/CN/ngay nghi); `days` > 1 thi lui them tung ngay lam viec."""
    holidays = set(holidays or ())
    d = chosen if chosen and chosen < boundary else boundary - _dt.timedelta(days=1)
    d = _business(d, -1, holidays)
    for _ in range(max(1, days) - 1):
        d = _business(d - _dt.timedelta(days=1), -1, holidays)
    return d


def business_day_after(chosen, boundary, holidays=(), days=1):
    holidays = set(holidays or ())
    d = chosen if chosen and chosen > boundary else boundary + _dt.timedelta(days=1)
    d = _business(d, 1, holidays)
    for _ in range(max(1, days) - 1):
        d = _business(d + _dt.timedelta(days=1), 1, holidays)
    return d


# ---------------------------------------------------------------- ma doi tac
_COMPANY_STOP = {"CONG", "TY", "CO", "PHAN", "TNHH", "TRACH", "NHIEM", "HUU", "HAN", "MOT", "THANH",
                 "VIEN", "THUONG", "MAI", "VA", "DICH", "VU"}


def initials(name):
    return "".join(w[0] for w in strip_accents(name).split() if w).upper() or "CREATOR"


def company_code(name):
    words = [w for w in re.split(r"[^A-Z0-9]+", strip_accents(name).upper()) if w and w not in _COMPANY_STOP]
    if not words:
        return initials(name)
    if len(words) == 1:
        return words[0][:8]
    return "".join(w[0] for w in words)[:8]


def party_code(creator_type, name, manual=""):
    """Ma doi tac trong so hop dong: Ke toan dien tay thi dung, khong thi suy tu ten (nhu tool cu)."""
    code = (manual or "").strip().upper()
    if creator_type == "Hộ kinh doanh":
        ok = re.fullmatch(r"[A-Z0-9]{2,8}", code) and code != "HKD"
        bare = re.sub(r"^\s*HỘ\s+KINH\s+DOANH\s*[-:]?\s*", "", str(name or ""), flags=re.I)
        return code if ok else company_code(bare or name)
    if creator_type == "Công ty":
        ok = re.fullmatch(r"[A-Z0-9]{2,6}", code) and code != "CONGTY"
        return code if ok else company_code(name)
    return code or initials(name)


# ---------------------------------------------------------------- dinh dang
def round_half_up(value):
    """Lam tron toi dong, .5 len (Math.round cua tool cu). format()/round() cua Python lam tron chan."""
    from decimal import ROUND_HALF_UP, Decimal
    return int(Decimal(repr(float(value or 0))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def money(value):
    """1234567 -> '1,234,567' (dau phay - dung nhu cac hop dong da ky bang tool cu)."""
    return "{:,}".format(round_half_up(value))


def rate_pct(value):
    """10.0 -> '10', 1.5 -> '1.5' (mau viet '<<TNCN_RATE_PCT>>%')."""
    return "%g" % round(float(value or 0), 2)


def address(value):
    a = str(value or "").strip()
    a = re.sub(r"\s+,", ",", a)
    a = re.sub(r",{2,}", ",", a)
    a = re.sub(r"\s{2,}", " ", a)
    a = re.sub(r"[,.\s]+$", "", a)
    if not a:
        return ""
    return a if "VIET NAM" in strip_accents(a).upper() else a + ", Việt Nam"


def bank_branch(bank, branch):
    b, br = str(bank or "").strip(), str(branch or "").strip()
    if not br:
        return b
    if re.search(r"\b(cn|chi nhánh)\b", br, re.I):
        return b + " - " + br
    return b + " - CN " + br


def strip_honorific(name):
    return re.sub(r"^\s*(ông|bà|anh|chị)\s+", "", str(name or ""), flags=re.I).strip()


def quantity_text(quantity, kind):
    q = int(quantity or 1)
    num = "%02d" % q if q < 10 else str(q)
    return num + (" video" if kind == VIDEO else " hạng mục" if kind == HYBRID else " buổi")


def _d(d):
    return d.strftime("%d/%m/%Y")

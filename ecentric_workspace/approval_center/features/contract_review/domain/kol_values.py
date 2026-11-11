# Copyright (c) 2026, eCentric and contributors
"""Bang <<TEN>> -> gia tri de dien 18 mau HDDV/BBNT cua Ke toan (tool Google Sheet cu).

Anh Hoan chot 12/11/2026: dung lai nguyen 18 mau Google Docs dang chay, nen ERP dien DUNG bo ten
va DUNG cach tinh cua tool cu (prepareBooking_ trong Apps Script V5.0.3). Bo ten {{ten_tieng_viet}}
cu cua ERP bo han - chua mau nao dung toi.

Thuan Python, khong goi frappe. `creator` la ban ghi day du (co PII): chi goi tu server luc
sinh tep, khong tra ra client.
"""
import datetime as _dt

from ecentric_workspace.approval_center.features.contract_review.domain import kol_texts as T
from ecentric_workspace.approval_center.features.contract_review.domain.kol_work_texts import (
    advance_texts, work_texts)
from ecentric_workspace.approval_center.features.contract_review.domain.vn_words import amount_in_words

# Dong tuy chon cua mau co coc: gia tri rong -> XOA CA DOAN (removeBlankConditionalParagraphs_).
# Anh CCCD: ERP chua luu anh CCCD -> doan anh bi xoa, khong de lai <<...>> tren hop dong.
CONDITIONAL_LINES = ("ADVANCE_CUSTOM_DETAIL_LINE", "ADVANCE_VIDEO_DATE_LINE", "ADVANCE_VIDEO_CHANNEL_LINE",
                     "ADVANCE_VIDEO_DURATION_LINE", "ADVANCE_LIVE_SUMMARY_LINE", "ADVANCE_LIVE_DATE_LINE",
                     "ADVANCE_LIVE_DURATION_LINE", "ADVANCE_AFFILIATE_CLAUSE",
                     "PERSON_ID_FRONT_IMAGE", "PERSON_ID_BACK_IMAGE")

# Chi co o BBNT cua ERP (moi dot nghiem thu mot BBNT - hoa hong affiliate nhieu dot).
BBNT_ONLY = ("ACCEPTANCE_ROUND", "ACCEPTANCE_DESCRIPTION", "ACCEPTANCE_AMOUNT_NUM", "ACCEPTANCE_AMOUNT_WORDS")

# Mau DUNG toi ma gia tri RONG = hop dong co cho trong -> bao thieu, khong cho gui.
REQUIRED_WHEN_USED = {
    "_all": ("CONTRACT_NO", "SIGN_DAY", "SIGN_DATE_DOT", "SIGN_DATE_SLASH", "BRAND", "CHANNEL_URL",
             "PARTY_ADDRESS", "BANK_ACCOUNT_NO", "BANK_NAME_SHORT", "BANK_NAME_BRANCH", "BANK_ACCOUNT_HOLDER",
             "SIGNATORY_B_UPPER", "SERVICE_START_SLASH", "SERVICE_DATES_DISPLAY", "BBNT_DAY"),
    "Cá nhân": ("PERSON_FULL_NAME", "PERSON_ID_NO", "PERSON_DOB"),
    "Công ty": ("COMPANY_LEGAL_NAME", "PARTY_TAX_ID", "COMPANY_REPRESENTATIVE_DISPLAY",
                "COMPANY_REPRESENTATIVE_TITLE"),
    "Hộ kinh doanh": ("HOUSEHOLD_LEGAL_NAME", "PARTY_TAX_ID", "HOUSEHOLD_REPRESENTATIVE_DISPLAY"),
}

# Nhan tieng Viet cho thong bao "hop dong con thieu ..." (trang chi hien nhan, khong hien ten ky thuat).
LABELS = {
    "PERSON_FULL_NAME": "họ tên creator", "PERSON_ID_NO": "CCCD", "PERSON_DOB": "ngày sinh",
    "PERSON_EMAIL": "email", "PERSON_PHONE": "số điện thoại", "PARTY_ADDRESS": "địa chỉ", "PARTY_TAX_ID": "MST",
    "COMPANY_LEGAL_NAME": "tên công ty", "COMPANY_REPRESENTATIVE_DISPLAY": "người đại diện",
    "COMPANY_REPRESENTATIVE_TITLE": "chức vụ người đại diện", "HOUSEHOLD_LEGAL_NAME": "tên hộ kinh doanh",
    "HOUSEHOLD_REPRESENTATIVE_DISPLAY": "chủ hộ", "BANK_ACCOUNT_NO": "số tài khoản",
    "BANK_NAME_SHORT": "ngân hàng", "BANK_NAME_BRANCH": "ngân hàng / chi nhánh", "BANK_ACCOUNT_HOLDER": "chủ tài khoản",
    "SIGNATORY_B_UPPER": "người ký bên B", "CHANNEL_URL": "link kênh", "TIKTOK_ID_DISPLAY": "TikTok ID",
    "SHOPEE_ID_DISPLAY": "Shopee ID", "BRAND": "brand", "CONTRACT_NO": "số hợp đồng",
    "SERVICE_START_SLASH": "ngày thực hiện", "SERVICE_DATES_DISPLAY": "ngày thực hiện",
    "SIGN_DAY": "ngày ký", "SIGN_DATE_DOT": "ngày ký", "SIGN_DATE_SLASH": "ngày ký", "BBNT_DAY": "ngày BBNT",
    "ADVANCE_PERCENT": "tỷ lệ cọc (mẫu có cọc nhưng phiếu không cọc - chọn lại mẫu)",
    "ADVANCE_AMOUNT_NUM": "tiền cọc", "ADVANCE_AMOUNT_WORDS": "tiền cọc", "BALANCE_AMOUNT_NUM": "phần còn lại",
    "BALANCE_AMOUNT_WORDS": "phần còn lại",
}
# Ten kieu cu (truoc 12/11) con nam trong missing_placeholders cua phieu nhap 11/11.
LEGACY_LABELS = {"cccd": "CCCD", "ngay_cap": "ngày cấp CCCD", "noi_cap": "nơi cấp CCCD", "ngay_sinh": "ngày sinh",
                 "dia_chi": "địa chỉ", "mst": "MST", "so_tai_khoan": "số tài khoản", "ngan_hang": "ngân hàng",
                 "chi_nhanh": "chi nhánh ngân hàng", "chu_tai_khoan": "chủ tài khoản", "dien_thoai": "số điện thoại",
                 "email": "email", "nguoi_dai_dien": "người đại diện", "chuc_vu": "chức vụ", "tiktok_id": "TikTok ID",
                 "link_kenh": "link kênh", "shopee_id": "Shopee ID", "ten_creator": "tên creator",
                 "ma_brand": "mã brand", "so_hop_dong": "số hợp đồng", "ngay_ky": "ngày ký"}
LEGACY_CREATOR = {"cccd", "ngay_cap", "noi_cap", "ngay_sinh", "dia_chi", "mst", "so_tai_khoan", "ngan_hang",
                  "chi_nhanh", "chu_tai_khoan", "dien_thoai", "email", "nguoi_dai_dien", "chuc_vu", "tiktok_id",
                  "link_kenh", "shopee_id", "ten_creator"}
CREATOR_FIELDS = ("PERSON_FULL_NAME", "PERSON_ID_NO", "PERSON_DOB", "PERSON_EMAIL", "PERSON_PHONE",
                  "PARTY_ADDRESS", "PARTY_TAX_ID", "COMPANY_LEGAL_NAME", "COMPANY_REPRESENTATIVE_DISPLAY",
                  "COMPANY_REPRESENTATIVE_TITLE", "HOUSEHOLD_LEGAL_NAME", "HOUSEHOLD_REPRESENTATIVE_DISPLAY",
                  "BANK_ACCOUNT_NO", "BANK_NAME_SHORT", "BANK_NAME_BRANCH", "BANK_ACCOUNT_HOLDER",
                  "SIGNATORY_B_UPPER", "CHANNEL_URL", "TIKTOK_ID_DISPLAY", "SHOPEE_ID_DISPLAY")


def _date(v):
    if not v:
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    return _dt.date.fromisoformat(str(v)[:10])


def _fmt(d, kind):
    if not d:
        return ""
    return {"dd": "%02d" % d.day, "mm": "%02d" % d.month, "yyyy": str(d.year),
            "dot": d.strftime("%d.%m.%Y"), "slash": d.strftime("%d/%m/%Y")}[kind]


def _money_block(creator_type, doc):
    """Cac con so theo dung calculateMoney_ cua tool cu (cong ty: GROSS = tong da VAT)."""
    gross, pit = float(doc.get("gross_amount") or 0), float(doc.get("pit_amount") or 0)
    vat, payable = float(doc.get("vat_amount") or 0), float(doc.get("payable_amount") or 0)
    if creator_type == "Công ty":
        return {"gross": payable, "net": payable, "pre_vat": gross, "vat": vat, "total": payable}
    if creator_type == "Hộ kinh doanh":
        return {"gross": payable, "net": payable, "pre_vat": payable, "vat": 0.0, "total": payable}
    return {"gross": gross, "net": payable, "pre_vat": gross, "vat": 0.0, "total": payable, "pit": pit}


def _num_words(prefix, value, out, blank_zero=False):
    if blank_zero and not value:
        out[prefix + "_NUM"] = out[prefix + "_WORDS"] = ""
        return
    out[prefix + "_NUM"] = T.money(value)
    out[prefix + "_WORDS"] = amount_in_words(value)


def contract_values(doc, creator, brand_code, sign_date, service_dates, bbnt_date=None,
                    payment_days=30, shopee_hddv_days=30):
    """doc = phieu (dict, tien da tinh), creator = Supplier day du. Tra {TEN: chuoi}."""
    ctype = doc.get("creator_type") or creator.get("ec_cr_type") or ""
    shopee = (doc.get("platform") or "") == T.SHOPEE
    kind = T.service_kind(doc.get("service_type"))
    brand = doc.get("brand") or ""
    name = creator.get("supplier_name") or ""
    tiktok = (creator.get("ec_cr_tiktok_id") or "").lstrip("@")
    shopee_id = creator.get("ec_cr_shopee_id") or ""
    channel_url = (creator.get("ec_cr_shopee_url") if shopee else creator.get("ec_cr_channel_url")) or (
        ("https://shopee.vn/" + shopee_id if shopee_id else "") if shopee
        else ("https://www.tiktok.com/@" + tiktok if tiktok else ""))
    dates = list(service_dates or [])
    first, last = (dates[0], dates[-1]) if dates else (None, None)
    if not dates:
        # Hop dong cu (truoc 12/11) ghi ngay dang chu tu do khong doc duoc: BBNT van lam duoc - lay
        # nguyen van chu + ngay bat dau / ket thuc tren phieu (QC 12/11).
        first, last = _date(doc.get("contract_start_date")), _date(doc.get("contract_end_date"))
    quantity = int(float(doc.get("quantity") or len(dates) or 1))
    # "Yeu cau bo sung" (service_detail cua tool cu): form 27 chua co o rieng -> de trong, dong
    # ADVANCE_CUSTOM_DETAIL_LINE bi xoa ca doan nhu tool cu khi rong.
    duration, custom = doc.get("duration") or "", doc.get("service_detail") or ""
    work = work_texts(kind, brand, channel_url, dates, quantity, duration, custom, shopee) if dates else {}
    adv = advance_texts(kind, brand, channel_url, dates, quantity, duration, custom) if dates else {}
    rep = (creator.get("ec_cr_representative_name") or "").strip()
    signatory = T.strip_honorific(rep) if ctype in ("Công ty", "Hộ kinh doanh") else name
    m = _money_block(ctype, doc)
    is_person, is_company, is_hkd = ctype == "Cá nhân", ctype == "Công ty", ctype == "Hộ kinh doanh"
    days_by_type = {"PERSONAL": payment_days if is_person else 35,
                    "HOUSEHOLD": payment_days if is_hkd else 30}
    sign, bbnt = _date(sign_date), _date(bbnt_date)
    out = {
        "CONTRACT_NO": doc.get("contract_no") or "", "BRAND": brand,
        "PLATFORM": "Shopee" if shopee else "TikTok",
        "SIGN_DAY": _fmt(sign, "dd"), "SIGN_MONTH": _fmt(sign, "mm"), "SIGN_YEAR": _fmt(sign, "yyyy"),
        "SIGN_DATE_DOT": _fmt(sign, "dot"), "SIGN_DATE_SLASH": _fmt(sign, "slash"),
        "BBNT_DAY": _fmt(bbnt, "dd"), "BBNT_MONTH": _fmt(bbnt, "mm"), "BBNT_YEAR": _fmt(bbnt, "yyyy"),
        "BBNT_DATE_DOT": _fmt(bbnt, "dot"), "BBNT_DATE_SLASH": _fmt(bbnt, "slash"),
        "SERVICE_START_SLASH": _fmt(first, "slash"), "SERVICE_END_SLASH": _fmt(last, "slash"),
        "SERVICE_START_DOT": _fmt(first, "dot"), "SERVICE_END_DOT": _fmt(last, "dot"),
        "SERVICE_DATES_DISPLAY": "\n".join(d.strftime("%d.%m.%Y") for d in dates) or (doc.get("air_dates") or ""),
        "QUANTITY_DISPLAY": T.quantity_text(quantity, kind),
        "TIKTOK_ID_DISPLAY": tiktok, "SHOPEE_ID_DISPLAY": shopee_id,
        "CHANNEL_ID_DISPLAY": shopee_id if shopee else tiktok, "CHANNEL_URL": channel_url,
        "PERSON_FULL_NAME": name if is_person else "",
        "PERSON_ID_NO": (creator.get("ec_cr_cccd") or "") if is_person else "",
        "PERSON_DOB": _fmt(_date(creator.get("ec_cr_dob")), "slash") if is_person else "",
        "PERSON_EMAIL": (creator.get("ec_cr_email") or "") if is_person else "",
        "PERSON_PHONE": (creator.get("ec_phone") or "") if is_person else "",
        "PERSON_ID_ISSUE_DATE": _fmt(_date(creator.get("ec_cr_cccd_issue_date")), "slash") if is_person else "",
        "PERSON_ID_ISSUE_PLACE": (creator.get("ec_cr_cccd_issue_place") or "") if is_person else "",
        "PERSON_ID_FRONT_LINK": "", "PERSON_ID_BACK_LINK": "",
        "PERSON_ID_FRONT_IMAGE": "", "PERSON_ID_BACK_IMAGE": "",
        "COMPANY_LEGAL_NAME": name if is_company else "",
        "COMPANY_REPRESENTATIVE_DISPLAY": rep if is_company else "",
        "COMPANY_REPRESENTATIVE_TITLE": (creator.get("ec_cr_representative_title") or "") if is_company else "",
        "HOUSEHOLD_LEGAL_NAME": name if is_hkd else "",
        "HOUSEHOLD_REPRESENTATIVE_DISPLAY": rep if is_hkd else "",
        "HOUSEHOLD_REPRESENTATIVE_TITLE": (creator.get("ec_cr_representative_title") or "Chủ hộ kinh doanh")
        if is_hkd else "",
        "PARTY_ADDRESS": T.address(creator.get("ec_cr_address")),
        "PARTY_TAX_ID": creator.get("tax_id") or "",
        "BANK_ACCOUNT_HOLDER": creator.get("ec_cr_account_holder") or name,
        "BANK_ACCOUNT_NO": creator.get("ec_bank_account_no") or "",
        "BANK_NAME_SHORT": (creator.get("ec_bank_name") or "").strip(),
        "BANK_NAME_BRANCH": T.bank_branch(creator.get("ec_bank_name"), creator.get("ec_cr_bank_branch")),
        "SIGNATORY_B_UPPER": (signatory or name).upper(),
        "TNCN_RATE_PCT": T.rate_pct(doc.get("pit_rate") if doc.get("pit_rate") not in (None, "") else 10),
        "VAT_RATE_PCT": T.rate_pct(doc.get("vat_rate") if doc.get("vat_rate") not in (None, "") else 8),
        "PAYMENT_DAYS": str(payment_days),
        "PAYMENT_DAYS_PERSONAL": str(days_by_type["PERSONAL"]),
        "PAYMENT_DAYS_HOUSEHOLD": str(days_by_type["HOUSEHOLD"]),
        # Tool cu: ngoai Shopee hai ten nay lay so ngay CONG TY (mau cong ty dung) - phieu cong ty
        # sua so ngay thi theo phieu, loai khac giu 30 nhu tool cu.
        "PAYMENT_DAYS_HDDV": str(shopee_hddv_days if shopee else (payment_days if is_company else 30)),
        "PAYMENT_DAYS_BBNT": str(payment_days if (shopee or is_company) else 30),
        "ADVANCE_PERCENT": T.rate_pct(doc.get("advance_percent")) if doc.get("advance_amount") else "",
    }
    _num_words("GROSS_AMOUNT", m["gross"], out)
    _num_words("NET_AMOUNT", m["net"], out)
    _num_words("PRE_VAT_AMOUNT", m["pre_vat"], out)
    _num_words("VAT_AMOUNT", m["vat"], out)
    _num_words("TOTAL_AMOUNT", m["total"], out)
    advance = float(doc.get("advance_amount") or 0)
    _num_words("ADVANCE_AMOUNT", advance, out, blank_zero=True)
    _num_words("BALANCE_AMOUNT", (m["total"] - advance) if advance else 0, out, blank_zero=True)
    for key, src in (("SERVICE_TITLE_SHORT", "titleShort"), ("SERVICE_TYPE_DISPLAY", "serviceDisplay"),
                     ("SERVICE_ACTION_DISPLAY", "serviceAction"), ("OBJECT_PARAGRAPH", "objectParagraph"),
                     ("WORK_CONTENT_PARAGRAPH", "workParagraph"), ("WORK_CONTENT_PREFIX", "workPrefix"),
                     ("DETAIL_PARAGRAPH", "detailParagraph"), ("DURATION_LABEL", "durationLabel"),
                     ("DURATION_DISPLAY", "durationDisplay"), ("MIN_PRODUCT_LABEL", "minProductLabel"),
                     ("MIN_PRODUCT_DISPLAY", "minProductDisplay"), ("RESULT_USAGE_CLAUSE", "resultUsageClause"),
                     ("PRODUCT_INFO_CLAUSE", "productInfoClause"), ("BBNT_WORK_DESCRIPTION", "bbntWorkDescription"),
                     ("BBNT_WORK_DESCRIPTION_SHORT", "bbntWorkDescriptionShort"),
                     ("BBNT_PAYMENT_DESCRIPTION", "bbntPaymentDescription"), ("QUANTITY_HEADER", "quantityHeader")):
        out[key] = work.get(src, "")
    for key, src in (("ADVANCE_SERVICE_SUBTITLE", "subtitle"), ("ADVANCE_WORK_PARAGRAPH", "workParagraph"),
                     ("ADVANCE_CUSTOM_DETAIL_LINE", "customDetailLine"), ("ADVANCE_PACKAGE_QUANTITY", "packageQuantity"),
                     ("ADVANCE_DETAIL_INTRO", "detailIntro"), ("ADVANCE_VIDEO_DATE_LINE", "videoDateLine"),
                     ("ADVANCE_VIDEO_CHANNEL_LINE", "videoChannelLine"),
                     ("ADVANCE_VIDEO_DURATION_LINE", "videoDurationLine"),
                     ("ADVANCE_LIVE_SUMMARY_LINE", "liveSummaryLine"), ("ADVANCE_LIVE_DATE_LINE", "liveDateLine"),
                     ("ADVANCE_LIVE_DURATION_LINE", "liveDurationLine"), ("ADVANCE_AFFILIATE_CLAUSE", "affiliateClause")):
        out[key] = adv.get(src, "")
    return out


def round_money(creator_type, payable, pit_rate, vat_rate, doc=None):
    """So tien cua MOT DOT nghiem thu: `payable` = so tra creator cua dot (nhu tran chi DNTT).
    Quy nguoc theo dung cong thuc tool cu (ca nhan: thuc nhan -> gross; cong ty: da VAT ->
    truoc VAT)."""
    pay = T.round_half_up(payable)
    doc = doc or {}
    advance = float(doc.get("advance_amount") or 0)
    if creator_type == "Công ty" and advance:
        # Coc cong ty tinh tren gia tri TRUOC VAT -> toan bo VAT nam o phan con lai. Chia phan con
        # lai (truoc VAT con lai + VAT) cho cac dot theo ty le, de cong cac BBNT khop hoa don (QC 12/11).
        total = float(doc.get("payable_amount") or 0)
        rest = total - advance
        rest_pre = float(doc.get("gross_amount") or 0) - advance
        pre = T.round_half_up(rest_pre * pay / rest) if rest > 0 else pay
        return {"gross": pay, "net": pay, "pre_vat": pre, "vat": pay - pre, "total": pay}
    if creator_type == "Công ty":
        vr = float(8 if vat_rate in (None, "") else vat_rate) / 100.0
        pre = T.round_half_up(pay / (1 + vr))
        return {"gross": pay, "net": pay, "pre_vat": pre, "vat": pay - pre, "total": pay}
    if creator_type == "Hộ kinh doanh":
        return {"gross": pay, "net": pay, "pre_vat": pay, "vat": 0, "total": pay}
    pr = float(10 if pit_rate in (None, "") else pit_rate) / 100.0
    gross = T.round_half_up(pay / (1 - pr)) if pr < 1 else pay
    return {"gross": gross, "net": pay, "pre_vat": gross, "vat": 0, "total": pay}


def is_whole_round(doc, amount):
    """Mot dot duy nhat phu het hop dong (ke ca hop dong coc: dot = phan con lai sau coc) -> BBNT
    xac nhan 100% hop dong nhu tool cu, in so cua CA hop dong."""
    payable = float(doc.get("payable_amount") or 0)
    advance = float(doc.get("advance_amount") or 0)
    rows = doc.get("acceptances") or []
    amount = float(amount or 0)
    return abs(amount - payable) <= 0.5 or (len(rows) <= 1 and abs(amount + advance - payable) <= 0.5)


def printed_amount(doc, amount):
    """So tien tra creator IN tren BBNT cua dot (de may kiem ban ky tim dung con so)."""
    return float(doc.get("payable_amount") or 0) if is_whole_round(doc, amount) else float(amount or 0)


def acceptance_values(contract, row, doc=None):
    """BBNT mot dot = gia tri hop dong + thong tin dot (ngay BBNT = ngay nghiem thu cua dot).

    18 mau BBNT cua tool cu in GROSS/NET/TOTAL... (khong co ten rieng cho dot): dot nghiem thu
    KHONG phai toan bo hop dong (hoa hong nhieu dot, nghiem thu tung phan) thi cac so do tinh lai
    theo so tien cua dot - mot BBNT khong duoc xac nhan / cam ket tra ca hop dong (QC 12/11)."""
    out = dict(contract)
    amount = float(row.get("amount") or 0)
    out.update({"ACCEPTANCE_ROUND": str(row.get("idx") or ""),
                "ACCEPTANCE_DESCRIPTION": row.get("description") or ""})
    _num_words("ACCEPTANCE_AMOUNT", amount, out, blank_zero=True)
    doc = doc or {}
    payable = float(doc.get("payable_amount") or 0)
    if amount and payable and not is_whole_round(doc, amount):
        m = round_money(doc.get("creator_type"), amount, doc.get("pit_rate"), doc.get("vat_rate"), doc)
        for key, val in (("GROSS_AMOUNT", m["gross"]), ("NET_AMOUNT", m["net"]), ("PRE_VAT_AMOUNT", m["pre_vat"]),
                         ("VAT_AMOUNT", m["vat"]), ("TOTAL_AMOUNT", m["total"])):
            _num_words(key, val, out)
    return out


def _all_keys():
    blank = {"creator_type": "Cá nhân", "service_type": "Livestream"}
    return contract_values(blank, {}, "", None, [_dt.date(2026, 1, 1)])


PLACEHOLDER_HELP = sorted(set(_all_keys()) | set(BBNT_ONLY))


def known(kind_is_bbnt):
    keys = set(PLACEHOLDER_HELP)
    return keys if kind_is_bbnt else keys - set(BBNT_ONLY)


# Mau CO COC: tien coc / con lai rong = phieu khong coc dung nham mau coc (QC 12/11).
ADVANCE_REQUIRED = ("ADVANCE_PERCENT", "ADVANCE_AMOUNT_NUM", "ADVANCE_AMOUNT_WORDS",
                    "BALANCE_AMOUNT_NUM", "BALANCE_AMOUNT_WORDS")


# Hoa hong affiliate tinh theo ky - khong bat buoc ngay buoi live (mau affiliate cua Ke toan co the
# van in cac ten nay; de trong thi khong chan).
DATE_FIELDS = ("SERVICE_START_SLASH", "SERVICE_DATES_DISPLAY")


def empty_required(values, used, creator_type, service_type=None):
    need = set(REQUIRED_WHEN_USED["_all"]) | set(REQUIRED_WHEN_USED.get(creator_type, ())) | set(ADVANCE_REQUIRED)
    if service_type == "Hoa hồng affiliate":
        need -= set(DATE_FIELDS)
    return [k for k in used if k in need and not str(values.get(k) or "").strip()]


def missing_labels(names):
    out = []
    for n in names or ():
        bare = n.split(" (")[0].strip()
        if bare.startswith("{{"):
            label = bare + " (tên kiểu cũ trong mẫu - báo Kế toán đổi sang <<TÊN>>)"
        else:
            bare = bare.strip("<>")
            label = LABELS.get(bare) or LEGACY_LABELS.get(bare) or "<<%s>>" % bare
        if "(không điền được)" in n:
            label += " (mẫu bị lỗi định dạng ở chỗ này - báo Kế toán sửa mẫu)"
        if label not in out:
            out.append(label)
    return out


def missing_is_creator(names):
    keys = {n.split(" (")[0].strip().strip("<>") for n in names or ()}
    return bool(keys & (set(CREATOR_FIELDS) | LEGACY_CREATOR))

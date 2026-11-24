# Copyright (c) 2026, eCentric and contributors
"""Creator master (KOL/KOC) - quy tac thuan, khong goi frappe.

Creator la `Supplier` cua ERPNext trong nhom CREATOR_GROUP (chot 11/11/2026, plan
"Hop dong KOL/KOC len ERP"): Payment Entry / cong no NCC ve sau noi thang vao day, khong
dung so song song.

Hai muc trung (anh Hoan chot 11/11):
- CUNG (chan): trung CCCD, MST hoac so tai khoan - chac chan la cung mot nguoi/phap nhan.
- MEM (hoi lai): trung ten, so dien thoai, TikTok ID hoac Shopee ID - co the la nguoi khac,
  nguoi tao xac nhan thi van tao duoc va ERP ghi lai da xac nhan voi ai.
"""
import re
import unicodedata

CREATOR_GROUP = "KOL/KOC Creator"
CREATOR_TYPES = ("Cá nhân", "Công ty", "Hộ kinh doanh")
SUPPLIER_TYPE_BY_CREATOR = {"Cá nhân": "Individual", "Công ty": "Company",
                            "Hộ kinh doanh": "Individual"}
MISA_PENDING_LABEL = "Đang cập nhật"
# Ma khach hang MISA (24/11/2026, nhap hang loat): MISA chi nhan ma chu / so khong dau, khong dau cach,
# toi da vai chuc ky tu (mau tren trang: "KH0123"). Them . _ - / cho ma kieu "KH-0123", "HN/0012".
MISA_CODE_MAX = 30
MISA_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

# Truong ca nhan nhay cam: chi chu ban ghi, EC Finance va System Manager thay ban day du.
PII_FIELDS = ("ec_cr_cccd", "ec_cr_cccd_issue_date", "ec_cr_cccd_issue_place", "ec_cr_dob",
              "ec_cr_address", "ec_cr_cccd_front", "ec_cr_cccd_back",
              "ec_bank_account_no", "ec_cr_bank_branch", "ec_cr_account_holder")
# Truong ai cung doc duoc (de tim va chon creator tren form hop dong).
PUBLIC_FIELDS = ("name", "supplier_name", "ec_cr_type", "ec_cr_party_code", "ec_cr_tiktok_id", "ec_cr_channel_url",
                 "ec_cr_shopee_id", "ec_cr_shopee_url", "ec_cr_misa_code", "ec_bank_name",
                 "ec_cr_representative_name", "ec_cr_representative_title")
# Truong lien lac + MST: khong cong khai, tra ve cho nguoi sua duoc ban ghi (chu / ke toan).
CONTACT_FIELDS = ("tax_id", "ec_phone", "ec_cr_email")
# Truong nguoi tao duoc ghi (ngoai ten va loai). Ma MISA KHONG nam day: chi ke toan ghi.
WRITABLE_FIELDS = ("tax_id", "ec_phone", "ec_cr_email", "ec_cr_party_code", "ec_cr_tiktok_id", "ec_cr_channel_url",
                   "ec_cr_shopee_id", "ec_cr_shopee_url", "ec_cr_representative_name",
                   "ec_cr_representative_title", "ec_bank_name") + PII_FIELDS

# Truong Data cua Frappe gioi han 140 ky tu: vuot thi insert loi giua chung, kiem truoc.
DATA_MAX = 140
LONG_FIELDS = ("ec_cr_address", "ec_cr_dup_ack")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

HARD_KEYS = ("ec_cr_cccd", "tax_id", "ec_bank_account_no")
# Truong nhan tien: doi sau khi da co hop dong = rui ro chuyen tien sai nguoi -> ghi vet tren ban ghi
# (ten truong + nguoi sua, KHONG ghi gia tri) de Ke toan thay (QC 15/11 D9 / A12).
PAYMENT_FIELDS = ("ec_bank_account_no", "ec_bank_name", "ec_cr_bank_branch", "ec_cr_account_holder", "tax_id")


def payment_changes(old, new):
    """Ten nhan (tieng Viet) cac truong nhan tien bi doi."""
    return [KEY_LABELS.get(f, f) for f in PAYMENT_FIELDS
            if f in new and str(new.get(f) or "").strip() != str(old.get(f) or "").strip()]
SOFT_KEYS = ("supplier_name", "ec_phone", "ec_cr_tiktok_id", "ec_cr_shopee_id")
KEY_LABELS = {"ec_cr_cccd": "CCCD", "tax_id": "MST", "ec_bank_account_no": "số tài khoản",
              "supplier_name": "tên", "ec_phone": "số điện thoại",
              "ec_cr_tiktok_id": "TikTok ID", "ec_cr_shopee_id": "Shopee ID",
              "ec_cr_channel_url": "link kênh TikTok", "ec_cr_shopee_url": "link Shopee",
              "ec_cr_email": "email", "ec_cr_cccd_issue_place": "nơi cấp CCCD",
              "ec_cr_representative_name": "người đại diện", "ec_cr_account_holder": "chủ tài khoản",
              "ec_cr_bank_branch": "chi nhánh", "ec_bank_name": "ngân hàng"}


def _digits(value):
    return re.sub(r"\D", "", str(value or ""))


def _fold(value):
    """Bo dau, ha chu, gop khoang trang - de so ten 'Nguyễn Thị A' voi 'nguyen thi  a'."""
    text = unicodedata.normalize("NFD", str(value or "")).replace("đ", "d").replace("Đ", "D")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text).strip().lower()


def display_handle(value):
    """TikTok/Shopee ID de IN (giu hoa thuong): bo '@', khoang trang, ?query, #, phan duong dan.
    Hop dong dung ham nay - ID luu dang URL tung in ra link hong '@https://...' (QC 15/11 A7)."""
    text = str(value or "").strip()
    text = re.split(r"[?#]", text, maxsplit=1)[0].rstrip("/")
    if "://" in text or text.lower().startswith("www.") or "/" in text:
        at = re.search(r"/@([^/]+)", text)
        text = at.group(1) if at else text.rsplit("/", 1)[-1]
    return re.sub(r"\s+", "", text).lstrip("@")


def _handle(value):
    """Ban ha chu cua display_handle de so trung.
    'https://www.tiktok.com/@abc/?lang=vi' -> 'abc' (truoc 11/11 thanh chuoi rong: khong so trung duoc)."""
    return display_handle(value).lower()


def _phone(value):
    """So VN ve dang 0xxxxxxxxx: +84 / 84 / 0084 / '+84 (0)912...'."""
    digits = _digits(value)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("84") and len(digits) > 9:
        digits = digits[2:]
        if not digits.startswith("0"):
            digits = "0" + digits
        digits = re.sub(r"^00", "0", digits)
    return digits


NORMALIZERS = {"ec_cr_cccd": _digits, "tax_id": _digits, "ec_bank_account_no": _digits,
               "supplier_name": _fold, "ec_phone": _phone,
               "ec_cr_tiktok_id": _handle, "ec_cr_shopee_id": _handle}


# Luu dang chuan hoa (chi so) de lan sau so trung va dien vao hop dong khong lech dinh dang.
STORE_NORMALIZED = {"ec_cr_cccd": _digits, "tax_id": _digits, "ec_bank_account_no": _digits,
                    # Ma viet tat trong so HD: bo moi khoang trang ("ntp vn" -> "NTPVN") - so HD khong
                    # duoc co dau cach. Ma sai khuon (cong ty > 6 ky tu...) thi so HD tu suy tu ten
                    # nhu tool cu (kol_texts.party_code), form ghi ro luat nay.
                    "ec_cr_party_code": lambda v: re.sub(r"\s+", "", str(v)).upper(),
                    "ec_phone": _phone}


def normalize_for_storage(values):
    out = dict(values)
    for field, fn in STORE_NORMALIZED.items():
        if out.get(field):
            out[field] = fn(out[field])
    return out


def normalize_key(field, value):
    return NORMALIZERS[field](value)


def identity_keys(data):
    """{field: gia tri da chuan hoa} cho cac truong dung de do trung, bo gia tri rong."""
    out = {}
    for field in HARD_KEYS + SOFT_KEYS:
        norm = normalize_key(field, data.get(field))
        if norm:
            out[field] = norm
    return out


_SAME_PERSON_TYPES = {"Cá nhân", "Hộ kinh doanh"}


def classify_duplicates(candidate, existing_rows):
    """So mot creator moi voi cac ban ghi co san (moi dong da co khoa chuan hoa).

    Tra {"hard": [...], "soft": [...]}; moi phan tu {"name", "supplier_name",
    "ec_cr_misa_code", "matched": [ten truong]}. Mot ban ghi da trung CUNG thi khong lap lai
    o nhom MEM."""
    mine = identity_keys(candidate)
    hard, soft = [], []
    for row in existing_rows:
        theirs = identity_keys(row)
        hit_hard = [f for f in HARD_KEYS if f in mine and mine[f] == theirs.get(f)]
        # MST ca nhan = so CCCD (tu 07/2025): CCCD cua nguoi nay la MST cua ban ghi kia = cung nguoi.
        for mine_f, their_f in (("ec_cr_cccd", "tax_id"), ("tax_id", "ec_cr_cccd")):
            if mine.get(mine_f) and mine[mine_f] == theirs.get(their_f) and mine_f not in hit_hard:
                hit_hard.append(mine_f)
        hit_soft = [f for f in SOFT_KEYS if f in mine and mine[f] == theirs.get(f)]
        if not (hit_hard or hit_soft):
            continue
        # `disabled` cua ban dang sua: chi tin so 1 (update cua Ke toan da chuan hoa) - chuoi "0" la truthy.
        if hit_hard and (row.get("disabled") or candidate.get("disabled") in (1, True)
                         or {candidate.get("ec_cr_type"), row.get("ec_cr_type")} == _SAME_PERSON_TYPES):
            # Creator da NGUNG DUNG: duong sua sai loai khi da co hop dong duyet = ngung creator cu, tao
            # creator dung loai (QC 17/11 vong 2) - chi hoi xac nhan.
            # Cung mot nguoi vua la creator ca nhan vua mo ho kinh doanh (MST = CCCD, chu ho thuong dung
            # chinh tai khoan ca nhan): chi hoi xac nhan, khong chan cung (PO 17/11). Cong ty <-> ca nhan
            # trung so tai khoan / ma so van CHAN cung (QC 17/11).
            hit_soft, hit_hard = hit_hard + hit_soft, []
        item = {"name": row.get("name"), "supplier_name": row.get("supplier_name"),
                "ec_cr_misa_code": row.get("ec_cr_misa_code") or MISA_PENDING_LABEL,
                "matched": hit_hard or hit_soft, "owner": row.get("owner")}
        (hard if hit_hard else soft).append(item)
    return {"hard": hard, "soft": soft}


def describe_match(item):
    labels = ", ".join(KEY_LABELS.get(f, f) for f in item["matched"])
    if not item.get("supplier_name"):
        return "một creator đã có (hỏi Kế toán để biết là ai) trùng %s" % labels
    return "%s (mã KH %s) trùng %s" % (item["supplier_name"], item["ec_cr_misa_code"], labels)


def mask_match(item, reveal):
    """Ban tra ve nguoi dung. Trung theo CCCD / STK / dien thoai ma nguoi do khong xem duoc PII cua
    ban ghi kia thi KHONG neu ten + ma KH: go thu so CCCD la do nguoc ra chu so (QC 15/11 D3).
    Trung theo ten (cong khai) van neu ten de nguoi lap chon dung creator co san."""
    out = {k: v for k, v in item.items() if k != "owner"}
    if not reveal and any(f != "supplier_name" for f in item.get("matched") or ()):
        out.update(name=None, supplier_name=None, ec_cr_misa_code=None)
    return out


def validate_payload(data):
    """Loi nhap lieu co ban - tra danh sach thong bao (rong = hop le)."""
    errors = []
    if not str(data.get("supplier_name") or "").strip():
        errors.append("Thiếu tên creator.")
    if data.get("ec_cr_type") not in CREATOR_TYPES:
        errors.append("Loại creator phải là: %s." % ", ".join(CREATOR_TYPES))
    cccd = _digits(data.get("ec_cr_cccd"))
    if cccd and len(cccd) not in (9, 12):
        errors.append("CCCD phải có 12 số (CMND cũ 9 số).")
    tax = _digits(data.get("tax_id"))
    if tax and len(tax) not in (10, 12, 13):
        errors.append("MST phải có 10 hoặc 13 số (MST cá nhân 12 số theo CCCD).")
    if data.get("ec_cr_type") == "Công ty" and not tax:
        errors.append("Creator là công ty thì phải có MST.")
    if data.get("ec_cr_type") == "Cá nhân" and not cccd:
        errors.append("Creator là cá nhân thì phải có CCCD.")
    if data.get("ec_cr_type") == "Hộ kinh doanh" and not (tax or cccd):
        errors.append("Hộ kinh doanh phải có MST (hoặc CCCD chủ hộ).")
    email = str(data.get("ec_cr_email") or "").strip()
    if email and not EMAIL.match(email):
        errors.append("Email không hợp lệ: %s." % email)
    long = [KEY_LABELS.get(f, f) for f, v in data.items()
            if f not in LONG_FIELDS and isinstance(v, str) and len(v) > DATA_MAX]
    if long:
        errors.append("Quá %d ký tự: %s (dán link rút gọn hoặc bỏ tham số sau dấu ?)."
                      % (DATA_MAX, ", ".join(sorted(long))))
    return errors


def misa_code_error(code):
    """Loi dinh dang ma MISA (chuoi da strip) hoac None. Dung chung nut Luu tung dong + nhap file."""
    if len(code) > MISA_CODE_MAX:
        return "Mã MISA dài quá %d ký tự." % MISA_CODE_MAX
    if not MISA_CODE_RE.match(code):
        return ("Mã MISA \"%s\" sai định dạng: chỉ dùng chữ không dấu, số và . _ - /, không dấu cách "
                "(vd KH0123)." % code)
    return None


def mask(value, keep=4):
    text = str(value or "")
    if not text:
        return ""
    return "•" * max(len(text) - keep, 3) + text[-keep:]


def public_view(row, can_see_pii):
    """Ban ghi tra cho client: truong cong khai + PII (day du hoac che)."""
    out = {f: row.get(f) for f in PUBLIC_FIELDS}
    out["misa_label"] = row.get("ec_cr_misa_code") or MISA_PENDING_LABEL
    if can_see_pii:   # lien lac / MST: tra cho nguoi sua duoc (thieu thi form sua xoa trang cac o nay)
        for f in CONTACT_FIELDS:
            out[f] = row.get(f)
    for f in PII_FIELDS:
        value = row.get(f)
        if can_see_pii:
            out[f] = value
        elif f in ("ec_cr_cccd", "ec_bank_account_no"):
            out[f] = mask(_digits(value))
    out["can_see_pii"] = bool(can_see_pii)
    out["disabled"] = 1 if row.get("disabled") else 0
    return out

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

# Truong ca nhan nhay cam: chi chu ban ghi, EC Finance va System Manager thay ban day du.
PII_FIELDS = ("ec_cr_cccd", "ec_cr_cccd_issue_date", "ec_cr_cccd_issue_place", "ec_cr_dob",
              "ec_cr_address", "ec_cr_cccd_front", "ec_cr_cccd_back",
              "ec_bank_account_no", "ec_cr_bank_branch", "ec_cr_account_holder")
# Truong ai cung doc duoc (de tim va chon creator tren form hop dong).
PUBLIC_FIELDS = ("name", "supplier_name", "ec_cr_type", "ec_cr_party_code", "ec_cr_tiktok_id", "ec_cr_channel_url",
                 "ec_cr_shopee_id", "ec_cr_shopee_url", "ec_cr_misa_code", "ec_bank_name",
                 "ec_cr_representative_name", "ec_cr_representative_title")
# Truong nguoi tao duoc ghi (ngoai ten va loai). Ma MISA KHONG nam day: chi ke toan ghi.
WRITABLE_FIELDS = ("tax_id", "ec_phone", "ec_cr_email", "ec_cr_party_code", "ec_cr_tiktok_id", "ec_cr_channel_url",
                   "ec_cr_shopee_id", "ec_cr_shopee_url", "ec_cr_representative_name",
                   "ec_cr_representative_title", "ec_bank_name") + PII_FIELDS

HARD_KEYS = ("ec_cr_cccd", "tax_id", "ec_bank_account_no")
SOFT_KEYS = ("supplier_name", "ec_phone", "ec_cr_tiktok_id", "ec_cr_shopee_id")
KEY_LABELS = {"ec_cr_cccd": "CCCD", "tax_id": "MST", "ec_bank_account_no": "số tài khoản",
              "supplier_name": "tên", "ec_phone": "số điện thoại",
              "ec_cr_tiktok_id": "TikTok ID", "ec_cr_shopee_id": "Shopee ID"}


def _digits(value):
    return re.sub(r"\D", "", str(value or ""))


def _fold(value):
    """Bo dau, ha chu, gop khoang trang - de so ten 'Nguyễn Thị A' voi 'nguyen thi  a'."""
    text = unicodedata.normalize("NFD", str(value or "")).replace("đ", "d").replace("Đ", "D")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text).strip().lower()


def _handle(value):
    """TikTok/Shopee ID: bo '@', khoang trang, phan duong dan; ha chu."""
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://\S*/@?", "", text)
    return text.lstrip("@").strip().rstrip("/")


def _phone(value):
    digits = _digits(value)
    if digits.startswith("84") and len(digits) > 9:
        digits = "0" + digits[2:]
    return digits


NORMALIZERS = {"ec_cr_cccd": _digits, "tax_id": _digits, "ec_bank_account_no": _digits,
               "supplier_name": _fold, "ec_phone": _phone,
               "ec_cr_tiktok_id": _handle, "ec_cr_shopee_id": _handle}


# Luu dang chuan hoa (chi so) de lan sau so trung va dien vao hop dong khong lech dinh dang.
STORE_NORMALIZED = {"ec_cr_cccd": _digits, "tax_id": _digits, "ec_bank_account_no": _digits,
                    "ec_cr_party_code": lambda v: str(v).strip().upper(),
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
        hit_soft = [f for f in SOFT_KEYS if f in mine and mine[f] == theirs.get(f)]
        if not (hit_hard or hit_soft):
            continue
        item = {"name": row.get("name"), "supplier_name": row.get("supplier_name"),
                "ec_cr_misa_code": row.get("ec_cr_misa_code") or MISA_PENDING_LABEL,
                "matched": hit_hard or hit_soft}
        (hard if hit_hard else soft).append(item)
    return {"hard": hard, "soft": soft}


def describe_match(item):
    labels = ", ".join(KEY_LABELS.get(f, f) for f in item["matched"])
    return "%s (mã KH %s) trùng %s" % (item["supplier_name"], item["ec_cr_misa_code"], labels)


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
    return errors


def mask(value, keep=4):
    text = str(value or "")
    if not text:
        return ""
    return "•" * max(len(text) - keep, 3) + text[-keep:]


def public_view(row, can_see_pii):
    """Ban ghi tra cho client: truong cong khai + PII (day du hoac che)."""
    out = {f: row.get(f) for f in PUBLIC_FIELDS}
    out["misa_label"] = row.get("ec_cr_misa_code") or MISA_PENDING_LABEL
    for f in PII_FIELDS:
        value = row.get(f)
        if can_see_pii:
            out[f] = value
        elif f in ("ec_cr_cccd", "ec_bank_account_no"):
            out[f] = mask(_digits(value))
    out["can_see_pii"] = bool(can_see_pii)
    return out
